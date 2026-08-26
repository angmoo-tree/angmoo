import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import { createServer as createNetServer } from "node:net";
import { fileURLToPath } from "node:url";

const downloadToken = "A".repeat(43);
const previewToken = "B".repeat(43);
const requests = [];

const upstream = createServer((request, response) => {
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    requests.push({
      method: request.method,
      path: request.url,
      headers: request.headers,
      body: Buffer.concat(chunks).toString("utf8"),
    });
    if (request.method === "DELETE") {
      response.writeHead(204);
      response.end();
      return;
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ proxied: true }));
  });
});
upstream.listen(0, "127.0.0.1");
await once(upstream, "listening");
const upstreamAddress = upstream.address();
assert.equal(typeof upstreamAddress, "object");

const frontendPort = await availablePort();
const command = process.execPath;
const nextCli = fileURLToPath(
  new URL("../node_modules/next/dist/bin/next", import.meta.url),
);
const next = spawn(
  command,
  [nextCli, "dev", "--hostname", "127.0.0.1", "--port", String(frontendPort)],
  {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: {
      ...process.env,
      ANGMOO_API_BASE_URL: `http://127.0.0.1:${upstreamAddress.port}`,
      NEXT_TELEMETRY_DISABLED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let logs = "";
next.stdout.on("data", (chunk) => {
  logs += chunk.toString();
});
next.stderr.on("data", (chunk) => {
  logs += chunk.toString();
});

const base = `http://127.0.0.1:${frontendPort}`;
try {
  await waitForNext(base);
  const cases = [
    {
      method: "GET",
      path: "/api/backend/world-package-exports/export-op/download",
      headers: {
        "X-World-Package-Download-Token": downloadToken,
        "X-World-Package-Delivery-Mode": "browser_download",
      },
      expected: {
        "x-world-package-download-token": downloadToken,
        "x-world-package-delivery-mode": "browser_download",
      },
    },
    {
      method: "POST",
      path: "/api/backend/world-package-exports/export-op/delivery-ack",
      headers: { "X-World-Package-Download-Token": downloadToken },
      expected: { "x-world-package-download-token": downloadToken },
    },
    {
      method: "DELETE",
      path: "/api/backend/world-package-exports/export-op",
      headers: { "X-World-Package-Download-Token": downloadToken },
      expected: { "x-world-package-download-token": downloadToken },
    },
    {
      method: "GET",
      path: "/api/backend/world-package-imports/import-op/preview",
      headers: { "X-World-Package-Preview-Token": previewToken },
      expected: { "x-world-package-preview-token": previewToken },
    },
    {
      method: "POST",
      path: "/api/backend/world-package-imports/import-op/commit",
      headers: {
        "Idempotency-Key": "proxy-smoke-idempotency",
        "X-World-Package-Preview-Token": previewToken,
      },
      body: JSON.stringify({ expected_content_digest: "digest" }),
      expected: {
        "idempotency-key": "proxy-smoke-idempotency",
        "x-world-package-preview-token": previewToken,
      },
    },
    {
      method: "DELETE",
      path: "/api/backend/world-package-imports/import-op",
      headers: { "X-World-Package-Preview-Token": previewToken },
      expected: { "x-world-package-preview-token": previewToken },
    },
  ];

  for (const testCase of cases) {
    const before = requests.length;
    const response = await proxyFetch(base, testCase);
    assert.ok(response.ok, `${testCase.method} ${testCase.path} returned ${response.status}`);
    assert.equal(requests.length, before + 1);
    const received = requests.at(-1);
    for (const [name, value] of Object.entries(testCase.expected)) {
      assert.equal(received.headers[name], value, `${name} was not forwarded exactly`);
    }
  }

  for (const invalid of [
    {
      method: "GET",
      path: "/api/backend/health",
      headers: { "X-World-Package-Download-Token": downloadToken },
    },
    {
      method: "GET",
      path: "/api/backend/world-package-exports/export-op/download",
      headers: { "X-World-Package-Download-Token": "not-a-capability" },
    },
    {
      method: "GET",
      path: "/api/backend/world-package-exports/export-op/download",
      headers: {
        "X-World-Package-Download-Token": downloadToken,
        "X-World-Package-Delivery-Mode": "unsupported",
      },
    },
  ]) {
    const before = requests.length;
    const response = await proxyFetch(base, invalid);
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), {
      detail: "world_package_proxy_capability_invalid",
    });
    assert.equal(requests.length, before, "invalid capability reached upstream");
  }

  assert.ok(
    requests.every(
      (request) =>
        !JSON.stringify(request.headers).includes("not-a-capability") &&
        !JSON.stringify(request.headers).includes("unsupported"),
    ),
  );
  console.log("world_package_proxy_capability_smoke_pass");
} finally {
  await stopChild(next);
  upstream.close();
  await once(upstream, "close");
}

async function proxyFetch(base, testCase) {
  const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes(testCase.method);
  return fetch(`${base}${testCase.path}`, {
    method: testCase.method,
    headers: {
      ...(testCase.headers ?? {}),
      ...(unsafe
        ? {
            Origin: base,
            "Sec-Fetch-Site": "same-origin",
            "Content-Type": "application/json",
          }
        : {}),
    },
    body: testCase.body,
  });
}

async function waitForNext(base) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (next.exitCode !== null) {
      throw new Error(`Next exited before readiness (${next.exitCode}).\n${logs}`);
    }
    try {
      const response = await fetch(`${base}/`, { redirect: "manual" });
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
  const port = address.port;
  server.close();
  await once(server, "close");
  return port;
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
    });
  } else {
    child.kill("SIGTERM");
  }
  await Promise.race([
    once(child, "exit"),
    new Promise((resolve) => setTimeout(resolve, 5_000)),
  ]);
}
