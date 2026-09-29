import base64
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from mylibrary.github import GitHubClient, GitHubError, capture_url, parse_url, source_open
from mylibrary.storage import read_json

BASE = "/repos/owner/repo"
PR = BASE + "/pulls/7"
DISCUSSION = BASE + "/issues/7/comments?per_page=100"
REVIEW = BASE + "/pulls/7/comments?per_page=100"
URL = "https://github.com/owner/repo/pull/7"


def reply(body, etag="v1", link=""):
    return 200, {"etag": etag, "link": link}, body


def comment(identifier, body="Comment", review=False):
    result = {"id": identifier, "body": body, "html_url": URL + f"#issuecomment-{identifier}",
              "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z",
              "user": {"login": "wayne"}, "issue_url": "https://api.github.com" + BASE + "/issues/7"}
    if review:
        result.update(path="src/core.py", diff_hunk="@@ -1 +1 @@\n-old\n+new", commit_id="a" * 40,
                      original_commit_id="b" * 40, in_reply_to_id=12, line=2, side="RIGHT",
                      pull_request_url="https://api.github.com" + PR)
    return result


class ScriptedClient:
    def __init__(self, replies):
        self.replies = {path: list(values) for path, values in replies.items()}
        self.calls = []

    def get(self, path, headers=None):
        self.calls.append((path, headers or {}))
        if path not in self.replies or not self.replies[path]:
            raise AssertionError(f"Unexpected request {path}")
        result = self.replies[path].pop(0)
        if isinstance(result, Exception):
            raise result
        status, response_headers, body = result
        return status, dict(response_headers), json.loads(json.dumps(body))


class Response:
    def __init__(self, url, body, headers=None):
        self.url, self.status = url, 200
        self.headers = headers or {}
        self.content = json.dumps(body).encode()

    def read(self, limit):
        return self.content[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "vault"
        self.vault.mkdir()

    def test_pr_three_independent_paginated_sources_preserve_review_location(self):
        following = REVIEW + "&page=2"
        client = ScriptedClient({
            PR: [reply({"id": 7, "number": 7, "title": "Fix context", "body": "Why this matters"})],
            DISCUSSION: [reply([comment(1)])],
            REVIEW: [reply([comment(2, review=True)], link=f'<https://api.github.com{following}>; rel="next"')],
            following: [reply([comment(3, "Second review", True)])],
        })
        captured = capture_url(self.vault, URL, client)
        self.assertEqual(captured["input_kind"], "source_update")
        self.assertEqual(captured["authorship"], "source_observation")
        self.assertEqual(captured["coverage"]["status"], "complete")
        self.assertEqual(captured["coverage"]["endpoints"]["review_comments"]["pages"], 2)
        review = captured["semantic"]["review_comments"][1]
        self.assertEqual(review["path"], "src/core.py")
        self.assertEqual(review["commit_id"], "a" * 40)
        self.assertEqual(review["in_reply_to_id"], 12)
        self.assertIn("@@ -1 +1 @@", review["diff_hunk"])
        raw = read_json(self.vault / captured["raw_path"])
        self.assertEqual(raw["responses"][following][0]["updated_at"], "2026-09-02T00:00:00Z")
        self.assertIn("Second review", (self.vault / captured["body_path"]).read_text())
        self.assertEqual([path for path, _ in client.calls], [PR, DISCUSSION, REVIEW, following])

    def test_endpoint_etag_does_not_hide_another_endpoint_update(self):
        client = ScriptedClient({
            PR: [reply({"title": "Context", "body": "Body"}, "pr"), (304, {}, None)],
            DISCUSSION: [reply([], "discussion"), (304, {}, None)],
            REVIEW: [reply([comment(1, "Old", True)], "review1"), reply([comment(1, "New", True)], "review2")],
        })
        first = capture_url(self.vault, URL, client)
        second = capture_url(self.vault, URL, client)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["revision"], first["revision"] + 1)
        self.assertEqual(client.calls[-3:],[
            (PR, {"If-None-Match": "pr"}), (DISCUSSION, {"If-None-Match": "discussion"}),
            (REVIEW, {"If-None-Match": "review1"})])
        self.assertIn("New", (self.vault / second["body_path"]).read_text())

    def test_304_first_page_still_checks_all_cached_pages(self):
        following = DISCUSSION + "&page=2"
        client = ScriptedClient({
            PR: [reply({"title": "Context", "body": "Body"}), (304, {}, None)],
            DISCUSSION: [reply([comment(1)], link=f'<https://api.github.com{following}>; rel="next"'), (304, {}, None)],
            following: [reply([comment(2, "Before")]), reply([comment(2, "After")])],
            REVIEW: [reply([]), (304, {}, None)],
        })
        first = capture_url(self.vault, URL, client)
        second = capture_url(self.vault, URL, client)
        self.assertEqual(second["revision"], first["revision"] + 1)
        self.assertIn("After", (self.vault / second["body_path"]).read_text())
        self.assertEqual(second["coverage"]["endpoints"]["discussion"]["pages"], 2)

    def test_partial_failure_does_not_claim_all_discussion(self):
        client = ScriptedClient({PR: [reply({"title": "Readable", "body": "Body"})],
                                 DISCUSSION: [GitHubError("GitHub HTTP 403", status=403)], REVIEW: [reply([])]})
        captured = capture_url(self.vault, URL, client)
        self.assertEqual(captured["coverage"]["status"], "partial")
        self.assertEqual(captured["coverage"]["gaps"], ["discussion"])
        self.assertEqual(captured["coverage"]["endpoints"]["discussion"]["status"], "unreachable")
        self.assertEqual(captured["semantic"]["coverage"]["discussion"], "unreachable")
        self.assertIn("Readable", (self.vault / captured["body_path"]).read_text())

    def test_file_is_pinned_to_commit_and_historical_reads_are_local(self):
        sha_a, sha_b = "a" * 40, "b" * 40
        file_a, file_b = BASE + "/contents/src/core.py?ref=" + sha_a, BASE + "/contents/src/core.py?ref=" + sha_b
        url = "https://github.com/owner/repo/blob/main/src/core.py"
        client = ScriptedClient({BASE + "/commits/main": [reply({"sha": sha_a}), reply({"sha": sha_b})],
                                 BASE + "/commits/main%2Fsrc": [GitHubError("GitHub HTTP 404", status=404), GitHubError("GitHub HTTP 404", status=404)],
                                 file_a: [reply({"type": "file", "encoding": "base64", "sha": "c" * 40,
                                                 "content": base64.b64encode(b"old source\n").decode()})],
                                 file_b: [reply({"type": "file", "encoding": "base64", "sha": "d" * 40,
                                                 "content": base64.b64encode(b"new source\n").decode()})]})
        first = capture_url(self.vault, url, client)
        second = capture_url(self.vault, url, client)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["semantic"]["commit_sha"], sha_a)
        self.assertEqual(second["semantic"]["blob_sha"], "d" * 40)
        self.assertEqual((self.vault / first["attachments"][0]["path"]).read_bytes(), b"old source\n")
        with patch("mylibrary.github.GitHubClient", side_effect=AssertionError("No network")):
            old = source_open(self.vault, first["source_id"], "historical", 1)
            cached = source_open(self.vault, url, "cache")
        self.assertEqual(Path(old["body_path"]).read_text(), "old source\n")
        self.assertEqual(Path(cached["body_path"]).read_text(), "new source\n")
        self.assertEqual(old["freshness"]["status"], "historical")

    def test_branch_with_slash_is_resolved_without_guessing_first_segment(self):
        sha = "a" * 40
        client = ScriptedClient({BASE + "/commits/feature%2Fcontext": [reply({"sha": sha})],
                                 BASE + "/contents/notes.md?ref=" + sha: [reply({"type": "file", "sha": "b" * 40,
                                     "encoding": "base64", "content": base64.b64encode(b"Branch text").decode()})]})
        result = capture_url(self.vault, "https://github.com/owner/repo/blob/feature/context/notes.md", client)
        self.assertEqual(result["semantic"]["requested_ref"], "feature/context")
        self.assertEqual(result["semantic"]["path"], "notes.md")
        self.assertEqual(result["identity"]["resource_id"], "file:feature/context:notes.md")

    def test_large_or_binary_file_uses_git_blob_without_external_download(self):
        commit, blob = "a" * 40, "c" * 40
        binary = b"\x00\xffbinary"
        client = ScriptedClient({BASE + "/commits/main": [reply({"sha": commit})],
                                 BASE + "/contents/data.bin?ref=" + commit: [reply({"type": "file", "encoding": "none", "sha": blob})],
                                 BASE + "/git/blobs/" + blob: [reply({"sha": blob, "encoding": "base64", "content": base64.b64encode(binary).decode()})]})
        captured = capture_url(self.vault, "https://github.com/owner/repo/blob/main/data.bin", client)
        self.assertEqual((self.vault / captured["attachments"][0]["path"]).read_bytes(), binary)
        self.assertTrue(all(path.startswith(BASE) for path, _ in client.calls))

    def test_explicit_comments_keep_separate_identity_and_verify_parent(self):
        issue, review = comment(13), comment(14, review=True)
        client = ScriptedClient({BASE + "/issues/comments/13": [reply(issue)],
                                 BASE + "/pulls/comments/14": [reply(review)]})
        first = capture_url(self.vault, "https://github.com/owner/repo/issues/7#issuecomment-13", client)
        second = capture_url(self.vault, URL + "#discussion_r14", client)
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["semantic"]["comment"]["original_commit_id"], "b" * 40)
        wrong = dict(issue, issue_url="https://api.github.com" + BASE + "/issues/99")
        with self.assertRaisesRegex(GitHubError, "does not belong"):
            capture_url(self.vault, "https://github.com/owner/repo/issues/7#issuecomment-13",
                        ScriptedClient({BASE + "/issues/comments/13": [reply(wrong)]}))

    def test_commit_file_pagination_preserves_specific_sha_and_patches(self):
        sha = "a" * 40
        endpoint = BASE + "/commits/" + sha + "?per_page=100"
        following = endpoint + "&page=2"
        metadata = {"sha": sha, "commit": {"message": "Why this changed"}}
        client = ScriptedClient({endpoint: [reply(dict(metadata, files=[{"filename": "first.py", "patch": "first"}]),
                                                  link=f'<https://api.github.com{following}>; rel="next"')],
                                 following: [reply(dict(metadata, files=[{"filename": "second.py", "patch": "second"}]))]})
        captured = capture_url(self.vault, "https://github.com/owner/repo/commit/" + sha, client)
        self.assertEqual(captured["semantic"]["commit_sha"], sha)
        self.assertEqual([item["filename"] for item in captured["semantic"]["files"]], ["first.py", "second.py"])
        self.assertEqual(captured["coverage"]["endpoints"]["commit"]["pages"], 2)

    def test_abbreviated_commit_maps_to_same_full_commit_identity(self):
        sha = "a" * 40
        short = sha[:7]
        payload = {"sha": sha, "commit": {"message": "Same commit"}, "files": []}
        client = ScriptedClient({BASE + "/commits/" + short + "?per_page=100": [reply(payload)],
                                 BASE + "/commits/" + sha + "?per_page=100": [reply(payload)]})
        short_url = "https://github.com/owner/repo/commit/" + short
        first = capture_url(self.vault, short_url, client)
        second = capture_url(self.vault, "https://github.com/owner/repo/commit/" + sha, client)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(second["revision"], 1)
        self.assertEqual(source_open(self.vault, short_url)["source_id"], first["source_id"])

    def test_strict_url_and_pagination_boundary(self):
        for url in ("/Users/wayne/repo", "file:///etc/passwd", "http://github.com/o/r/pull/1",
                    "https://github.com.evil/o/r/pull/1", "https://u:p@github.com/o/r/pull/1",
                    "https://github.com/o/r/tree/main", "https://github.com/o/r/blob/main/../secrets"):
            with self.assertRaises(ValueError):
                parse_url(url)
        client = ScriptedClient({PR: [reply({"title": "Safe", "body": "Data"})], DISCUSSION: [reply([])],
                                 REVIEW: [reply([comment(1, review=True)], link='<https://evil.example/data>; rel="next"')]})
        captured = capture_url(self.vault, URL, client)
        self.assertEqual(captured["coverage"]["status"], "partial")
        self.assertEqual(len(client.calls), 3)
        with self.assertRaises(GitHubError):
            GitHubClient(token="sentinel").get("https://evil.example/repos/o/r")

    def test_cache_and_if_stale_never_capture_unknown_reference(self):
        with patch("mylibrary.github.GitHubClient", side_effect=AssertionError("No network")):
            self.assertEqual(capture_url(self.vault, URL, mode="cache")["status"], "not_cached")
            self.assertEqual(capture_url(self.vault, URL, mode="if-stale")["status"], "not_cached")
        client = ScriptedClient({PR: [reply({"title": "Safe", "body": "Data"})], DISCUSSION: [reply([])], REVIEW: [reply([])]})
        captured = capture_url(self.vault, URL, client)
        with patch("mylibrary.github.GitHubClient", side_effect=AssertionError("Fresh cache should not network")):
            opened = source_open(self.vault, captured["event_id"], mode="if-stale")
        self.assertEqual(opened["source"]["event_id"], captured["event_id"])

    def test_authentication_token_never_enters_source_results_or_cache(self):
        token = "private-credential-sentinel"

        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout):
                self.requests.append(request)
                payload = [] if request.full_url.endswith("comments?per_page=100") else {"title": "Read", "body": "Data"}
                return Response(request.full_url, payload, {"etag": "safe", "Authorization": token})

        opener = Opener()
        client = GitHubClient(token=token, opener=opener)
        result = capture_url(self.vault, URL, client)
        self.assertTrue(all(request.get_header("Authorization") == "Bearer " + token for request in opener.requests))
        self.assertNotIn(token, json.dumps(result))
        self.assertTrue(all(token.encode() not in path.read_bytes() for path in self.vault.rglob("*") if path.is_file()))
        self.assertTrue(all(request.full_url.startswith("https://api.github.com/repos/owner/repo/") for request in opener.requests))

    def test_rate_limit_defers_without_leaking_response_body(self):
        token = "private-credential-sentinel"

        class Opener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 429, "limited", {"Retry-After": "120"}, BytesIO(token.encode()))

        with self.assertRaises(GitHubError) as raised:
            GitHubClient(token=token, opener=Opener()).get(PR)
        self.assertEqual(raised.exception.status, 429)
        self.assertIsNotNone(raised.exception.retry_at)
        self.assertNotIn(token, str(raised.exception))

    def test_rate_limit_stops_remaining_endpoint_requests(self):
        client = ScriptedClient({PR: [reply({"title": "Context", "body": "Body"})],
                                 DISCUSSION: [GitHubError("Rate limited", status=429, retry_at=time.time() + 120)]})
        captured = capture_url(self.vault, URL, client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(captured["coverage"]["gaps"], ["discussion", "review_comments"])
        self.assertIsNotNone(captured["coverage"]["endpoints"]["review_comments"]["retry_at"])


if __name__ == "__main__":
    unittest.main()
