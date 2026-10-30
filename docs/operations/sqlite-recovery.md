# SQLite recovery and retained results

> **Legacy scope:** this records the SQLite runtime through 0.1.3 and preserved migration input. For 0.1.4 use [PostgreSQL runtime](../public/postgresql-runtime.md), [migration](../public/postgresql-migration.md), and [backup](../public/postgresql-backup.md). Historical findings below remain unchanged.

SQLite remains canonical. Graph, FTS and Vec1 are disposable projections, not
alternative sources of authorization or completion. Do not reset queues, delete
pending work, increase all busy timeouts, or regenerate paid outputs to clear a
temporary contention condition.

- `SQLITE_BUSY` and extended BUSY codes enter the bounded admission policy.
  `SQLITE_LOCKED`, malformed image JSON, path/permission defects and unsupported
  payloads require diagnosis. The SQLite helper emits safe attempt timing/code
  facts at debug level; worker logs identify the stage without source content.
- A graph effect whose acknowledgement contends remains lease-owned. Expired
  leases can replay idempotently without counting local contention as a poison
  payload attempt. Readiness only recovers after actual backlog health recovers.
  A confirmed graph failure still records a pending retry and consumes the next
  attempt when claimed; eight failed attempts, terminal errors and the existing
  age limit retain their dead-letter policy. Reclaim alone is not such proof.
- Situation receipts commit one at a time. Relationship target/period roots use
  complete read preparation followed by fresh source/consent validation. Work
  remains resumable; schedule-spacing advice does not replace these guarantees.
- Received relationship-review and embedding results are stored privately under
  `MEDIA_ROOT/private-result-journals`, outside public media routes. Each World
  namespace is bounded to 512 records / 16 MiB, with 256 KiB per record. Results
  exist only while delivery is pending and are removed after delivery or erasure.
  Content-free closed-item/World markers deliberately outlive the result so a
  late response cannot recreate erased content. Permission/size/corruption errors
  are not authorization to issue another paid request. A relationship submission
  marker without a durable response becomes outcome-unknown after restart.
- World erasure reuses its request and cleanup journal. A historical file entry
  without a generation identity is retained if the path exists: it cannot prove
  that this is still the file originally inventoried. Other Worlds' references,
  character originals and draft assets take priority over freeing storage.
- Existing failed World requests are resumed by the owner through **Retry deletion**, after the underlying failure is resolved. An agent does not reset
  production failures or delete their files as a regression test.
- Image diagnostics describe observed HTTP facts only. A 502, read timeout and
  local SQLite busy are different failures. The current generation timeout and
  unknown-outcome policy are unchanged; successful diagnostic collection does not
  resolve an earlier provider outage.

Before inspecting an installed Windows app or its DB, verify the actual
opened installation and data paths. When available, follow the installed-app
diagnostic procedure; do not assume an AppData alias resolves to the active files. Local checkout tests, hosted CI, main
merge, image/installer deployment and real-AI quality provide distinct kinds of evidence.
