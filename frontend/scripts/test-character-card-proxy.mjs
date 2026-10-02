import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { createServer as createNetServer } from "node:net";
import { fileURLToPath } from "node:url";

const defaultLimit = 1024 * 1024;
const cardLimit = 28_000_000 + 256 * 1024;
const cardPath = "/api/backend/agents/drafts/draft-test/card";
const received = [];

const upstream = createServer(async (request, response) => {
  const digest = createHash("sha256");
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.byteLength;
    digest.update(chunk);
  }
  const entry = {
    path: request.url,
    method: request.method,
    bytes,
    sha256: digest.digest("hex"),
  };
  received.push(entry);
  response.writeHead(200, { "content-type": "application/json",
    ...(request.url.includes("/card-source") ? {
      "cache-control": "private, no-store", "x-content-type-options": "nosniff",
      "x-private-diagnostic": "must-not-be-forwarded",
    } : {}),
  });
  response.end(JSON.stringify(entry));
});
upstream.listen(0, "127.0.0.1");
await once(upstream, "listening");
const upstreamAddress = upstream.address();
assert.equal(typeof upstreamAddress, "object");

const frontendPort = await availablePort();
const nextCli = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const next = spawn(process.execPath, [nextCli, "dev", "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
  cwd: fileURLToPath(new URL("..", import.meta.url)),
  env: {
    ...process.env,
    ANGMOO_API_BASE_URL: `http://127.0.0.1:${upstreamAddress.port}`,
    NEXT_TELEMETRY_DISABLED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let logs = "";
for (const stream of [next.stdout, next.stderr]) {
  stream.on("data", (chunk) => { logs = (logs + chunk.toString()).slice(-10_000); });
}
const base = `http://127.0.0.1:${frontendPort}`;

try {
  await waitForNext();
  const payload = (bytes) => Buffer.alloc(bytes, 0x61);
  const sakanaSized = payload(1_911_730);

  // A Sakana-sized transport body must reach the card endpoint unchanged
  // through the actual Next route handler.
  await forwarded(cardPath, sakanaSized);
  await forwarded(cardPath, payload(cardLimit));
  await rejected(cardPath, payload(cardLimit + 1));
  await forwarded(cardPath, payload(cardLimit), { chunked: true });
  await forwarded(cardPath, payload(1_911_730), { chunked: true });
  await rejected(cardPath, payload(cardLimit + 1), { chunked: true });
  await forwarded(cardPath + "?source=card", sakanaSized);
  const summary = await fetch(base + "/api/backend/agents/drafts/draft-test/card-source?include_document=false");
  assert.equal(summary.status, 200);
  assert.equal(summary.headers.get("cache-control"), "private, no-store");
  assert.equal(summary.headers.get("x-content-type-options"), "nosniff");
  assert.equal(summary.headers.get("x-private-diagnostic"), null);
  assert.equal((await summary.json()).path, "/api/v1/agents/drafts/draft-test/card-source?include_document=false");
  const beforeTrailingSlash = received.length;
  const trailingSlash = await proxyFetch(cardPath + "/", sakanaSized, { redirect: "manual" });
  assert.ok([307, 308].includes(trailingSlash.status));
  assert.equal(new URL(trailingSlash.headers.get("location"), base).pathname, cardPath);
  assert.equal(received.length, beforeTrailingSlash, "redirect forwarded the noncanonical path");

  await forwarded("/api/backend/posts", payload(defaultLimit));
  await rejected("/api/backend/posts", payload(defaultLimit + 1));
  for (const path of [
    "/api/backend/agents/drafts/draft-test/card-source",
    "/api/backend/agents/drafts/draft-test/card/extra",
    "/api/backend/agents/drafts/draft-test/copy-settings",
  ]) {
    await rejected(path, payload(defaultLimit + 1));
  }
  await rejected(cardPath, payload(defaultLimit + 1), { method: "PUT" });
  await forwarded("/api/backend/agents/agent-test/lore-sources", payload(defaultLimit + 1));
  await forwarded("/api/backend/agents/drafts/draft-test/media", payload(defaultLimit + 1));

  const before = received.length;
  const forbidden = await proxyFetch(cardPath, payload(256), { origin: "http://foreign.invalid" });
  assert.equal(forbidden.status, 403);
  assert.equal(received.length, before, "cross-origin request reached upstream");
  const missingOrigin = await proxyFetch(cardPath, payload(256), { origin: null });
  assert.equal(missingOrigin.status, 403);
  assert.equal(received.length, before, "request without Origin reached upstream");

  console.log("character_card_proxy_upload_pass");
} finally {
  await stopChild(next);
  upstream.close();
  await once(upstream, "close");
}

async function forwarded(path, body, options = {}) {
  const before = received.length;
  const response = await proxyFetch(path, body, options);
  assert.equal(response.status, 200, `${options.method ?? "POST"} ${path}: ${response.status}`);
  assert.equal(received.length, before + 1, `${path} did not reach upstream once`);
  const entry = await response.json();
  assert.equal(entry.bytes, body.byteLength);
  assert.equal(entry.sha256, createHash("sha256").update(body).digest("hex"));
  assert.equal(entry.method, options.method ?? "POST");
  assert.equal(entry.path, path.replace(/^\/api\/backend/, "/api/v1"));
}

async function rejected(path, body, options = {}) {
  const before = received.length;
  const response = await proxyFetch(path, body, options);
  assert.equal(response.status, 413, `${options.method ?? "POST"} ${path}: ${response.status}`);
  assert.deepEqual(await response.json(), { detail: "Request body exceeds the allowed limit." });
  assert.equal(received.length, before, `${path} reached upstream despite 413`);
}

function proxyFetch(path, body, options = {}) {
  const origin = options.origin === undefined ? base : options.origin;
  const headers = {
    ...(origin === null ? {} : { Origin: origin }),
    "Sec-Fetch-Site": origin === base || origin === null ? "same-origin" : "cross-site",
    "Content-Type": "application/json",
  };
  if (options.chunked) {
    return fetch(base + path, {
      method: options.method ?? "POST",
      headers,
      redirect: options.redirect ?? "follow",
      body: new ReadableStream({
        start(controller) {
          for (let offset = 0; offset < body.byteLength; offset += 64 * 1024) {
            controller.enqueue(body.subarray(offset, Math.min(offset + 64 * 1024, body.byteLength)));
          }
          controller.close();
        },
      }),
      duplex: "half",
    });
  }
  return fetch(base + path, { method: options.method ?? "POST", headers, body, redirect: options.redirect ?? "follow" });
}

async function waitForNext() {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (next.exitCode !== null) throw new Error(`Next exited before readiness (${next.exitCode}).\n${logs}`);
    try {
      const response = await fetch(base + "/", { redirect: "manual" });
      if (response.status > 0) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Next did not become ready.\n${logs}`);
}

async function availablePort() {
  const server = createNetServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert.equal(typeof address, "object");
  server.close();
  await once(server, "close");
  return address.port;
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
  await Promise.race([once(child, "exit"), new Promise((resolve) => setTimeout(resolve, 5_000))]);
}
