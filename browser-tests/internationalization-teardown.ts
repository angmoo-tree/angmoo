export default async function teardown() {
  // Let the owned contributor server release its SQLite scheduler/retention
  // leases before Playwright disposes its server process tree.
  await fetch("http://127.0.0.1:18399/__fixture/stop", {
    method: "POST", headers: {"x-fixture-control": "synthetic-only"},
  }).catch(() => {});
}
