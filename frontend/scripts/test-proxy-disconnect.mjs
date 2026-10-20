// Real Next request/response adapters, isolated ports and a synthetic upstream.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createServer, request as httpRequest } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { readFile, writeFile } from "node:fs/promises";

const configPath = new URL("../tsconfig.json", import.meta.url);
const originalConfig = await readFile(configPath, "utf8");

const seen = new Map(), closed = new Set();
const upstream = createServer((req, res) => {
  const name = req.url.split("?")[0].split("/").at(-1);
  seen.set(name, (seen.get(name) ?? 0) + 1);
  res.on("close", () => closed.add(name));
  if (name === "headers") return;
  if (name === "broken") {
    res.writeHead(200, { "content-type": "application/x-ndjson" });
    res.write('{"type":"partial"}\n');
    setTimeout(() => res.destroy(), 80);
    return;
  }
  if (name === "stream" || name === "committed") {
    res.writeHead(200, { "content-type": "application/octet-stream" });
    res.write("first chunk");
    return;
  }
  if (name === "unavailable") { res.destroy(); return; }
  if (name === "error") {
    res.writeHead(409, { "cache-control": "no-store", "x-content-type-options": "nosniff", "retry-after": "1" });
    res.end('{"detail":"fixture_conflict"}'); return;
  }
  res.end("ready");
});
upstream.listen(0, "127.0.0.1"); await once(upstream, "listening");
const portServer = createServer(); portServer.listen(0, "127.0.0.1"); await once(portServer, "listening");
const port = portServer.address().port;
await new Promise(resolve => portServer.close(resolve));
const base = `http://127.0.0.1:${port}`;
const next = spawn(process.execPath, [fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url)), "dev", "--hostname", "127.0.0.1", "--port", String(port)], {
  cwd: fileURLToPath(new URL("..", import.meta.url)),
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", ANGMOO_NEXT_DIST_DIR: ".next-proxy-disconnect", ANGMOO_API_BASE_URL: `http://127.0.0.1:${upstream.address().port}` },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});
let logs = "";
next.stdout.on("data", data => { logs += data; }); next.stderr.on("data", data => { logs += data; });
const waitUntil = async (condition, message) => {
  const deadline = Date.now() + 90_000;
  while (!(await condition())) {
    if (Date.now() > deadline || next.exitCode !== null) throw new Error(`${message}\n${logs}`);
    await new Promise(resolve => setTimeout(resolve, 50));
  }
};
try {
  await waitUntil(async () => { try { return (await fetch(`${base}/api/backend/ready`)).ok; } catch { return false; } }, "Next startup");
  const first = new AbortController();
  const headers = fetch(`${base}/api/backend/headers?private_query=secret`, { signal: first.signal }).catch(() => {});
  await waitUntil(() => seen.has("headers"), "headers request sent"); first.abort(); await headers;
  await waitUntil(() => closed.has("headers"), "header wait released upstream");
  for (const [name, method] of [["stream", "GET"], ["committed", "POST"]]) {
    const abort = new AbortController();
    const response = await fetch(`${base}/api/backend/${name}`, { method, signal: abort.signal,
      headers: method === "POST" ? { Origin: base, "Content-Type": "application/json" } : {}, body: method === "POST" ? "{}" : undefined });
    const reader = response.body.getReader(); assert.equal((await reader.read()).done, false);
    abort.abort(); await reader.cancel().catch(() => {});
    await waitUntil(() => closed.has(name), `${name} upstream released`);
    assert.equal(seen.get(name), 1, "no automatic mutation retry");
  }
  const broken = await fetch(`${base}/api/backend/broken`);
  assert.equal(broken.status, 200);
  await assert.rejects(broken.text(), "upstream failure must not become normal EOF");
  assert.equal((await fetch(`${base}/api/backend/unavailable`)).status, 502);
  const error = await fetch(`${base}/api/backend/error`);
  assert.equal(error.status, 409); assert.equal(error.headers.get("retry-after"), "1");
  assert.deepEqual(await error.json(), { detail: "fixture_conflict" });
  // Interrupt upload while Next is still reading it: upstream must not see it.
  const upload = httpRequest(`${base}/api/backend/upload`, { method: "POST", headers: { Origin: base, "Content-Type": "application/octet-stream" } });
  upload.on("error", () => {}); upload.write(Buffer.alloc(32 * 1024));
  await new Promise(resolve => setTimeout(resolve, 150)); upload.destroy();
  await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(seen.has("upload"), false);
  assert.ok(logs.includes("backend_proxy_terminal"));
  const diagnostics = [...logs.matchAll(/\{\s*event: 'backend_proxy_terminal'[\s\S]*?\n\}/g)].map(match => match[0]).join("\n");
  assert.ok(diagnostics.length > 0);
  assert.ok(!diagnostics.includes("private_query"), "app diagnostics must not contain queries");
  assert.ok(!logs.includes("Error [ResponseAborted]"), logs);
  console.log("proxy_disconnect_pass: real Next header/stream/upload abort, POST once, broken NDJSON, 502, 409");
} finally {
  if (next.exitCode === null) {
    if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(next.pid), "/T", "/F"], { stdio: "ignore" });
    else next.kill("SIGTERM");
  }
  upstream.closeAllConnections(); await new Promise(resolve => upstream.close(resolve));
  // Next adds its temporary generated types. Restore only that known edit;
  // never overwrite a concurrent user change to the configuration.
  const current = JSON.parse(await readFile(configPath, "utf8"));
  current.include = current.include.filter(item => !item.startsWith(".next-proxy-disconnect/"));
  if (JSON.stringify(current) === JSON.stringify(JSON.parse(originalConfig))) await writeFile(configPath, originalConfig);
}
