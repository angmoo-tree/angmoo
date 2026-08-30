import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(join(root, "fixtures", "visual-corpus.json"), "utf8"),
);
const port = Number(process.env.ANGMOO_VISUAL_FIXTURE_PORT ?? "3302");
const nextProductOrigin = "http://127.0.0.1:3300";
const staticProductOrigin = "http://127.0.0.1:3301";

if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error("Visual fixture port must be between 1 and 65535.");
}

function sendJson(response, value, status = 200) {
  const body = JSON.stringify(value);
  response.writeHead(status, {
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
    "content-type": "application/json; charset=utf-8",
  });
  response.end(body);
}

function worldById(worldId) {
  return fixture.worlds.find((world) => world.world_id === worldId) ?? null;
}

const server = createServer((request, response) => {
  const origin = request.headers.origin;
  if (origin === nextProductOrigin) {
    response.setHeader("access-control-allow-origin", nextProductOrigin);
    response.setHeader("vary", "Origin");
  } else if (origin === staticProductOrigin) {
    response.setHeader("access-control-allow-origin", staticProductOrigin);
    response.setHeader("vary", "Origin");
  }
  if (origin === nextProductOrigin || origin === staticProductOrigin) {
    response.setHeader("access-control-allow-credentials", "true");
    response.setHeader("access-control-allow-headers", "content-type,x-angmoo-launcher-token");
    response.setHeader("access-control-allow-methods", "GET,HEAD,OPTIONS");
  }
  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    sendJson(response, { detail: "visual_fixture_is_read_only" }, 405);
    return;
  }

  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  if (url.pathname === "/health") {
    sendJson(response, { schema_version: fixture.schema_version, status: "ready" });
    return;
  }
  if (url.pathname === "/api/v1/auth/me") {
    sendJson(response, fixture.owner);
    return;
  }
  if (url.pathname === "/api/v1/runtime/status") {
    sendJson(response, fixture.runtime);
    return;
  }
  if (url.pathname === "/api/v1/agents") {
    sendJson(response, fixture.agents);
    return;
  }
  if (url.pathname === "/api/v1/maintenance/agent-activity") {
    sendJson(response, {
      enabled: false,
      title: "",
      message: "",
      blocks_auto_ticks: false,
      blocks_run_now: false,
      blocks_feed_cues: false,
      auto_tick_allowlist_active: false,
      auto_tick_allowed_count: 0,
      notice_enabled: false,
      notice_title: "",
      notice_message: "",
    });
    return;
  }
  if (/^\/api\/v1\/agents\/[^/]+\/feed-cue$/.test(url.pathname)) {
    sendJson(response, null);
    return;
  }
  if (
    url.pathname === "/api/v1/feed" ||
    url.pathname === "/api/v1/feed/following"
  ) {
    sendJson(response, fixture.global_feed);
    return;
  }
  if (url.pathname === "/api/v1/worlds/mine") {
    const surface = url.searchParams.get("surface");
    sendJson(response, {
      schema_version: "local-world-surface-v1",
      surface,
      items: fixture.worlds,
      next_cursor: null,
    });
    return;
  }

  const worldRead = url.pathname.match(/^\/api\/v1\/worlds\/mine\/([^/]+)$/);
  if (worldRead) {
    const world = worldById(decodeURIComponent(worldRead[1]));
    if (!world) {
      sendJson(response, { detail: "world_not_found" }, 404);
      return;
    }
    sendJson(response, {
      schema_version: "local-world-app-v1",
      surface: "world_app",
      world,
    });
    return;
  }

  const ownerCharacter = url.pathname.match(
    /^\/api\/v1\/worlds\/([^/]+)\/owner-character$/,
  );
  if (ownerCharacter) {
    const worldId = decodeURIComponent(ownerCharacter[1]);
    if (worldId !== fixture.owner_character.world_id) {
      sendJson(response, { detail: "owner_character_not_found" }, 404);
      return;
    }
    sendJson(response, fixture.owner_character);
    return;
  }

  const worldFeed = url.pathname.match(
    /^\/api\/v1\/worlds\/([^/]+)\/manual-social\/feed$/,
  );
  if (worldFeed) {
    const worldId = decodeURIComponent(worldFeed[1]);
    if (worldId !== fixture.world_feed.world_id) {
      sendJson(response, { detail: "world_feed_not_found" }, 404);
      return;
    }
    sendJson(response, fixture.world_feed);
    return;
  }

  if (url.pathname.endsWith("/relationship-graph")) {
    sendJson(response, fixture.graph);
    return;
  }

  sendJson(response, { detail: `unexpected_visual_fixture_request:${url.pathname}` }, 404);
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Angmoo UI-F visual fixture listening on ${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
