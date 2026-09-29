# Event integration reference

Use [consumer-interface.md](consumer-interface.md) for Event outcomes and [runtime-schema.md](runtime-schema.md) for the runnable staging contract.

The processing key is `(consumer, event_id, revision)`. Read frozen evidence, resolve stable Entities, stage supported replacement files, validate, and apply. A daily heading, Settle Log, copied note, or scanner checkpoint does not establish consumption.

Only successful outcomes backed by the completed apply receipt are terminal. Required evidence gaps and uncertain identities remain pending. Repeated apply returns the existing receipt. Interrupted apply uses `mylibrary recover <run_id>`. Publication retries separately.

Existing folder consumer configuration remains compatible. Use it only for explicitly requested legacy note-copy behavior, not as the Event receipt mechanism.
