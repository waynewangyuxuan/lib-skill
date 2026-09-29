"""Explicit GitHub source reads with endpoint-specific cache and evidence coverage."""

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .storage import Library, atomic_json, digest, read_json, timestamp, writer_lock

API_VERSION = "2026-03-10"


class GitHubError(RuntimeError):
    def __init__(self, message, *, status=None, retry_at=None):
        super().__init__(message)
        self.status = status
        self.retry_at = retry_at


def _api_path(value):
    if value.startswith("/") and not value.startswith("//"):
        parsed = urlsplit(value)
    else:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise GitHubError("GitHub API URL is outside api.github.com")
    if parsed.fragment or not parsed.path.startswith("/repos/") or ".." in unquote(parsed.path).split("/"):
        raise GitHubError("GitHub API path is outside the repository boundary")
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


class _Redirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        _api_path(newurl)
        if urlsplit(newurl).path.split("/")[2:4] != urlsplit(request.full_url).path.split("/")[2:4]:
            raise GitHubError("Redirect left the explicitly referenced repository")
        return super().redirect_request(request, response, code, message, headers, newurl)


def _credential():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    binary = shutil.which("gh")
    if binary:
        result = subprocess.run([binary, "auth", "token", "--hostname", "github.com"],
                                capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            return result.stdout.strip() or None
    return None


class GitHubClient:
    def __init__(self, token=None, opener=None):
        self._token = token if token is not None else _credential()
        self._opener = opener or build_opener(_Redirect())

    def get(self, path, headers=None):
        path = _api_path(path)
        request_headers = {"Accept": "application/vnd.github+json",
                           "X-GitHub-Api-Version": API_VERSION, "User-Agent": "mylibrary-tools"}
        request_headers.update(headers or {})
        if self._token:
            request_headers["Authorization"] = "Bearer " + self._token
        for attempt in range(3):
            try:
                request = Request("https://api.github.com" + path, headers=request_headers)
                with self._opener.open(request, timeout=30) as response:
                    _api_path(response.url)
                    body = response.read(100 * 1024 * 1024 + 1)
                    if len(body) > 100 * 1024 * 1024:
                        raise GitHubError("GitHub response exceeds 100 MiB")
                    return response.status, {key.lower(): value for key, value in response.headers.items()}, json.loads(body)
            except HTTPError as error:
                response_headers = {key.lower(): value for key, value in error.headers.items()}
                if error.code == 304:
                    return 304, response_headers, None
                if error.code in (403, 429):
                    retry_at = None
                    if "retry-after" in response_headers:
                        try:
                            retry_at = time.time() + max(0, float(response_headers["retry-after"]))
                        except ValueError:
                            retry_at = time.time() + 60
                    elif response_headers.get("x-ratelimit-remaining") == "0":
                        try:
                            retry_at = float(response_headers["x-ratelimit-reset"])
                        except (ValueError, KeyError):
                            retry_at = time.time() + 60
                    elif error.code == 429:
                        retry_at = time.time() + 60
                    if retry_at is not None:
                        raise GitHubError("GitHub rate limit; defer until retry_at", status=error.code, retry_at=retry_at) from None
                if error.code >= 500 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise GitHubError(f"GitHub HTTP {error.code}", status=error.code) from None
            except (URLError, TimeoutError, json.JSONDecodeError):
                raise GitHubError("GitHub response unavailable") from None
        raise GitHubError("GitHub retry limit reached")


def parse_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query
            or parsed.username or parsed.password):
        raise ValueError("Only explicit https://github.com source URLs are accepted")
    segments = parsed.path.strip("/").split("/")
    if len(segments) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", item) and item not in {".", ".."}
                                    for item in segments[:2]):
        raise ValueError("GitHub owner and repository required")
    owner, repo = (item.lower() for item in segments[:2])
    resource = {"owner": owner, "repo": repo, "workspace_id": f"github.com/{owner}/{repo}", "url": url}
    if len(segments) == 2 and not parsed.fragment:
        return dict(resource, kind="repository", resource_id="repository")
    if len(segments) >= 5 and segments[2] == "blob":
        ref, path = unquote(segments[3]), unquote("/".join(segments[4:]))
        if not ref or not path or any(part in {".", "..", ""} for part in path.split("/")):
            raise ValueError("Explicit file ref and confined repository path required")
        if parsed.fragment and not re.fullmatch(r"L[1-9][0-9]*(?:-L[1-9][0-9]*)?", parsed.fragment):
            raise ValueError("Unsupported file fragment")
        return dict(resource, kind="file", ref=ref, path=path, resource_id=f"file:{ref}:{path}")
    if len(segments) == 4 and segments[2] == "commit" and re.fullmatch(r"[0-9a-fA-F]{7,40}", segments[3]) and not parsed.fragment:
        return dict(resource, kind="commit", sha=segments[3].lower(), resource_id="commit:" + segments[3].lower())
    if len(segments) == 4 and segments[2] in {"pull", "issues"} and re.fullmatch(r"[1-9][0-9]*", segments[3]):
        number = int(segments[3])
        if parsed.fragment.startswith("issuecomment-") and re.fullmatch(r"issuecomment-[1-9][0-9]*", parsed.fragment):
            identifier = int(parsed.fragment.split("-", 1)[1])
            return dict(resource, kind="issue_comment", number=number, comment_id=identifier,
                        resource_id=f"issue_comment:{identifier}")
        if segments[2] == "pull" and re.fullmatch(r"discussion_r[1-9][0-9]*", parsed.fragment):
            identifier = int(parsed.fragment[len("discussion_r"):])
            return dict(resource, kind="review_comment", number=number, comment_id=identifier,
                        resource_id=f"review_comment:{identifier}")
        if segments[2] == "pull" and not parsed.fragment:
            return dict(resource, kind="pull", number=number, resource_id=f"pull:{number}")
    raise ValueError("Unsupported GitHub source URL")


def _source_id(resource):
    identity = {"provider": "github", "workspace_id": resource["workspace_id"], "resource_id": resource["resource_id"]}
    return "src_" + digest(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")))[:32]


def _next_link(value):
    for url, relation in re.findall(r'<([^>]+)>\s*;\s*rel="([^"]+)"', value or ""):
        if relation == "next":
            return _api_path(url)
    return None


class _Read:
    def __init__(self, client, cache, repository_path):
        self.client = client
        self.cache = dict(cache.get("endpoints", {}))
        self.repository_path = repository_path
        self.raw = {}
        self.coverage = {}
        self.retry_at = None

    def endpoint(self, path):
        if self.retry_at is not None and self.retry_at > time.time():
            raise GitHubError("GitHub rate limit; remaining endpoints deferred", retry_at=self.retry_at)
        path = _api_path(path)
        if not (path == self.repository_path or path.startswith(self.repository_path + "/")):
            raise GitHubError("Pagination left the explicitly referenced repository")
        cached = self.cache.get(path)
        headers = {"If-None-Match": cached["etag"]} if cached and cached.get("etag") else {}
        status, received, data = self.client.get(path, headers=headers)
        received = {key.lower(): value for key, value in received.items()}
        if status == 304:
            if not cached:
                raise GitHubError("304 without a cached endpoint response")
            data = cached["body"]
            link = received.get("link", cached.get("link", ""))
        elif status == 200:
            link = received.get("link", "")
        else:
            raise GitHubError(f"GitHub HTTP {status}", status=status)
        self.cache[path] = {"etag": received.get("etag", cached.get("etag") if cached else None),
                            "link": link, "body": data, "checked_at": timestamp()}
        self.raw[path] = data
        return data, _next_link(link)

    def read(self, label, path, paginated=False):
        pages, collected, seen, current = 0, [], set(), path
        try:
            while current:
                if urlsplit(current).path != urlsplit(path).path:
                    raise GitHubError("Pagination changed the explicit endpoint")
                if current in seen:
                    raise GitHubError("Pagination cursor repeated; coverage incomplete")
                seen.add(current)
                data, following = self.endpoint(current)
                pages += 1
                if paginated:
                    if not isinstance(data, list):
                        raise GitHubError("Paginated GitHub endpoint did not return a list")
                    collected.extend(data)
                else:
                    if not isinstance(data, dict):
                        raise GitHubError("GitHub resource did not return an object")
                    collected.append(data)
                current = following
            self.coverage[label] = {"status": "complete", "pages": pages, "items": len(collected)}
        except GitHubError as error:
            if error.retry_at is not None:
                self.retry_at = error.retry_at
            self.coverage[label] = {"status": "partial" if collected else "unreachable", "pages": pages,
                                    "items": len(collected), "continuation": current,
                                    "reason": str(error), "retry_at": error.retry_at}
        if paginated:
            return collected
        if not collected:
            return {}
        result = dict(collected[0])
        if "files" in result:
            result["files"] = [file for page in collected for file in page.get("files", [])]
        return result


def _comment(item, review=False):
    fields = ("id", "body", "html_url", "created_at", "path", "diff_hunk", "commit_id",
              "original_commit_id", "in_reply_to_id", "line", "original_line", "side",
              "start_line", "original_start_line", "start_side", "pull_request_review_id") if review else ("id", "body", "html_url", "created_at")
    return dict({key: item.get(key) for key in fields}, author=(item.get("user") or {}).get("login"))


def _comment_body(item, review=False):
    body = [f"### {'Review' if review else 'Discussion'} comment {item.get('id')}", item.get("html_url", ""), item.get("body") or ""]
    if review:
        body += [f"Code path: {item.get('path')}", f"Commit: {item.get('commit_id')}",
                 f"Reply to: {item.get('in_reply_to_id')}", "```diff", item.get("diff_hunk") or "", "```"]
    return "\n".join(body)


def capture_url(vault, url, client=None, mode="live"):
    if mode not in {"cache", "if-stale", "live"}:
        raise ValueError("Unknown GitHub capture policy")
    if mode != "live":
        return source_open(vault, url, mode=mode, client=client)
    resource = parse_url(url)
    library = Library(Path(vault))
    requested_source_id = _source_id(resource)
    alias_path = library._path("_sources/github-resources.json")
    aliases = read_json(alias_path) if alias_path.exists() else {}
    source_id = aliases.get(requested_source_id, requested_source_id)
    cache_path = library._path(f"_sources/{source_id}/http-cache.json")
    cache = read_json(cache_path) if cache_path.exists() else {}
    base = f"/repos/{resource['owner']}/{resource['repo']}"
    reader = _Read(client or GitHubClient(), cache, base)
    kind = resource["kind"]
    name, body, semantic, attachments = resource["resource_id"], "", {"kind": kind}, []
    if kind == "pull":
        number = resource["number"]
        pull = reader.read("pull_body", f"{base}/pulls/{number}")
        discussion = reader.read("discussion", f"{base}/issues/{number}/comments?per_page=100", True)
        reviews = reader.read("review_comments", f"{base}/pulls/{number}/comments?per_page=100", True)
        name = pull.get("title", name)
        if pull:
            body = f"# {name}\n{pull.get('body') or ''}\n"
        body += "\n\n".join(_comment_body(item) for item in discussion)
        body += "\n\n" + "\n\n".join(_comment_body(item, True) for item in reviews) if reviews else ""
        semantic.update(pull={key: pull.get(key) for key in ("id", "number", "title", "body", "state", "merged")},
                        discussion=[_comment(item) for item in discussion],
                        review_comments=[_comment(item, True) for item in reviews])
    elif kind in {"issue_comment", "review_comment"}:
        review = kind == "review_comment"
        endpoint = f"{base}/{'pulls' if review else 'issues'}/comments/{resource['comment_id']}"
        comment = reader.read(kind, endpoint)
        association = "pull_request_url" if review else "issue_url"
        expected = f"https://api.github.com{base}/{'pulls' if review else 'issues'}/{resource['number']}"
        if comment and comment.get(association, "").lower() != expected:
            raise GitHubError("Comment does not belong to the explicitly referenced issue or pull")
        if comment:
            body = _comment_body(comment, review)
            semantic["comment"] = _comment(comment, review)
    elif kind == "file":
        parts = resource["path"].split("/")
        commit = {}
        for split in range(len(parts) - 1, -1, -1):
            candidate_ref = "/".join([resource["ref"]] + parts[:split])
            candidate_path = "/".join(parts[split:])
            commit = reader.read("resolved_ref", base + "/commits/" + quote(candidate_ref, safe=""))
            if commit:
                resource.update(ref=candidate_ref, path=candidate_path,
                                resource_id=f"file:{candidate_ref}:{candidate_path}")
                source_id = _source_id(resource)
                cache_path = library._path(f"_sources/{source_id}/http-cache.json")
                break
            if reader.coverage["resolved_ref"].get("reason") != "GitHub HTTP 404":
                break
        commit_sha = commit.get("sha")
        if commit_sha and re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
            content = reader.read("file", base + "/contents/" + quote(resource["path"], safe="/") + "?ref=" + commit_sha)
            blob_sha = content.get("sha")
            if content and content.get("type") != "file":
                reader.coverage["file"]["status"] = "partial"
                reader.coverage["file"]["reason"] = "Referenced content is not a regular file"
            else:
                if content and content.get("encoding") != "base64" and blob_sha:
                    content = reader.read("blob", base + "/git/blobs/" + quote(blob_sha, safe=""))
                try:
                    binary = base64.b64decode("".join(content.get("content", "").split()), validate=True)
                    if not content or content.get("encoding") != "base64":
                        raise ValueError("No complete base64 file")
                    attachments = [{"id": resource["path"], "name": Path(resource["path"]).name, "content": binary}]
                    try:
                        body = binary.decode("utf-8")
                    except UnicodeDecodeError:
                        body = "Binary source file, read the preserved attachment bytes."
                    semantic.update(path=resource["path"], requested_ref=resource["ref"], commit_sha=commit_sha,
                                    blob_sha=blob_sha, content_sha256=digest(binary))
                    name = resource["path"]
                except (ValueError, TypeError):
                    reader.coverage["file"] = dict(reader.coverage.get("file", {}), status="partial", reason="File bytes unavailable or invalid")
        else:
            reader.coverage["file"] = {"status": "unreachable", "reason": "Commit ref could not be pinned"}
    elif kind == "commit":
        commit = reader.read("commit", base + "/commits/" + resource["sha"] + "?per_page=100")
        metadata = commit.get("commit") or {}
        name = (metadata.get("message") or resource["sha"]).split("\n", 1)[0]
        body = "# " + name + "\n" + (metadata.get("message") or "") if commit else ""
        semantic.update(commit_sha=commit.get("sha"), message=metadata.get("message"), parents=commit.get("parents", []))
        if re.fullmatch(r"[0-9a-fA-F]{40}", commit.get("sha", "")):
            resource["resource_id"] = "commit:" + commit["sha"].lower()
            source_id = _source_id(resource)
            cache_path = library._path(f"_sources/{source_id}/http-cache.json")
        semantic["files"] = commit.get("files", [])
        if len(commit.get("files", [])) >= 3000 or any("patch" not in item for item in commit.get("files", [])):
            reader.coverage["commit"]["status"] = "partial"
            reader.coverage["commit"]["reason"] = "File cap or missing patch evidence; no complete diff claim"
        reader.coverage["commit"]["scope"] = "commit metadata and returned file evidence"
    else:
        repository = reader.read("repository", base)
        name = repository.get("full_name", name)
        body = "# " + name + "\n" + (repository.get("description") or "") if repository else ""
        semantic["repository"] = {key: repository.get(key) for key in ("id", "full_name", "description", "default_branch", "archived")}
    gaps = [label for label, value in reader.coverage.items() if value["status"] != "complete"]
    coverage = {"status": "partial" if gaps else "complete", "gaps": gaps, "endpoints": reader.coverage}
    semantic["coverage"] = {label: value["status"] for label, value in reader.coverage.items()}
    observed = timestamp()
    with writer_lock(library.vault):
        aliases = read_json(alias_path) if alias_path.exists() else {}
        aliases[requested_source_id] = source_id
        atomic_json(alias_path, aliases)
        atomic_json(cache_path, {"schema_version": 1, "checked_at": observed,
                                "coverage": coverage, "endpoints": reader.cache})
    return library.record("github", resource["workspace_id"], resource["resource_id"], body,
                          name=name, input_kind="source_update", authorship="source_observation",
                          semantic=semantic, raw={"url": url, "responses": reader.raw},
                          attachments=attachments, coverage=coverage, source_url=url)


def source_open(vault, ref, mode="cache", revision=None, client=None):
    if mode not in {"cache", "historical", "live", "if-stale"}:
        raise ValueError("Unknown GitHub source policy")
    library = Library(Path(vault))
    desired = _source_id(parse_url(ref)) if ref.startswith("https://") else ref
    if not re.fullmatch(r"(?:src|evt)_[0-9a-f]{32}", desired):
        raise ValueError("GitHub source reference must be a known ID or explicit supported URL")
    alias_path = library._path("_sources/github-resources.json")
    if alias_path.exists():
        desired = read_json(alias_path).get(desired, desired)
    source = None
    for path in sorted(library._path("_events").glob("*/event.json")):
        event = read_json(library._path(path.relative_to(library.vault)))
        if event["identity"]["provider"] == "github" and desired in {event["source_id"], event["event_id"]}:
            source = event
            break
    if source is None:
        return {"status": "not_cached", "reference": ref, "mode": mode}
    cache_path = library._path(f"_sources/{source['source_id']}/http-cache.json")
    checked = read_json(cache_path).get("checked_at") if cache_path.exists() else None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked.replace("Z", "+00:00"))).total_seconds() if checked else None
    if mode == "live" or (mode == "if-stale" and (age is None or age >= 300)):
        source = capture_url(library.vault, source["source_url"], client=client)
        checked = read_json(cache_path).get("checked_at")
        age = 0
    if mode == "historical":
        if type(revision) is not int or revision < 1:
            raise ValueError("Historical reads require a positive numeric revision")
        path = library._path(f"_events/{source['event_id']}/revisions/{revision}/event.json")
        if not path.is_file():
            return {"status": "revision_not_cached", "revision": revision, "mode": mode}
        source = read_json(path)
    return {"status": "cached", "mode": mode, "source": source, "source_id": source["source_id"],
            "event_id": source["event_id"], "revision": source["revision"],
            "body_path": str(library._path(source["body_path"])),
            "raw_path": str(library._path(source["raw_path"])), "coverage": source["coverage"],
            "freshness": {"checked_at": checked, "age_seconds": age,
                          "status": "historical" if mode == "historical" else "observed" if age == 0 else "cached"}}
