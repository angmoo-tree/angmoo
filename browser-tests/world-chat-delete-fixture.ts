import type { Page, Route } from "@playwright/test";
import { FEED_WORLD } from "./world-feed-fixture";
import { installSocialChatFixture, SYNTHETIC_THREAD } from "./world-social-chat-fixture";

export async function installChatDeleteFixture(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const base = await installSocialChatFixture(page, staticShell, baseURL, language);
  const state = {
    base, count: 20, deleted: new Set<string>(), deleteRequests: [] as string[], reads: [] as string[],
    deleteMode: "ok" as "ok" | "409" | "500" | "offline" | "corrupt" | "wrong_world" | "wrong_thread" | "lost" | "401" | "403" | "404",
    delay: 0, listDelay: 0, longDiagnostics: false, activeResponse: false, ownerId: "local-owner" as string | null,
  };
  const thread = (id: string) => ({ ...base.thread, id,
    messages: id === SYNTHETIC_THREAD ? base.thread.messages : [],
    evidence_summaries: id === SYNTHETIC_THREAD ? base.thread.evidence_summaries : [],
  });
  const json = (route: Route, value: unknown, status = 200) => route.fulfill({ json: value, status });
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const collection = `/worlds/${FEED_WORLD}/chat/threads`;
    if (path === "/auth/me" && state.ownerId === null) return json(route, { detail: "Invalid token" }, 401);
    if (path === "/auth/me") return json(route, { id: state.ownerId, display_name: "Local Owner", email: null,
      profile_setup_completed: true, ui_language: base.base.language, ui_preference_revision: 1, feed_content_filter: "all", is_admin: true });
    if (request.method() === "GET") state.reads.push(path);
    if (path === collection && request.method() === "GET") {
      if (state.listDelay) await new Promise(resolve => setTimeout(resolve, state.listDelay));
      return json(route, { items: Array.from({ length: state.count }, (_, index) => thread(index ? `${SYNTHETIC_THREAD}-${index}` : SYNTHETIC_THREAD))
        .filter(item => !state.deleted.has(item.id)), ambiguous_legacy_count: 3, max_threads: null });
    }
    const exact = path.match(new RegExp(`^${collection}/([^/]+)$`));
    if (exact) {
      const id = exact[1];
      if (request.method() === "DELETE") {
        state.deleteRequests.push(id);
        const mode = state.deleteMode;
        if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
        if (mode === "offline") return route.abort("connectionreset");
        if (["409", "500", "401", "403", "404"].includes(mode)) return json(route, { detail: mode === "409" ? "world_chat_response_in_flight" : "fixture_delete_failed" }, Number(mode));
        if (mode === "corrupt") return route.fulfill({ contentType: "application/json", body: "{broken-json" });
        if (mode === "wrong_world" || mode === "wrong_thread") return json(route, { world_id: mode === "wrong_world" ? "other-world" : FEED_WORLD,
          thread_id: mode === "wrong_thread" ? "other-thread" : id, outcome: "deleted" });
        const outcome = state.deleted.has(id) ? "already_deleted" : "deleted";
        state.deleted.add(id);
        if (mode === "lost") return route.abort("connectionreset");
        return json(route, { world_id: FEED_WORLD, thread_id: id, outcome });
      }
      if (request.method() === "GET") return state.deleted.has(id) ? json(route, { detail: "thread_not_found" }, 404) : json(route, thread(id));
    }
    if (path.endsWith("/requests/latest") && state.activeResponse) {
      return json(route, { response_request: { protocol_version: "chat-generation-stream.v1", request_id: "active-delete-request",
        request_scope_hash: "a".repeat(64), generation_id: "active-delete-generation", attempt_number: 1,
        response_slot_id: "active-delete-slot", state: "response_generating", retryable: false, failure_class: null,
        last_accepted_sequence: -1, user_message: base.thread.messages[0], assistant_message: null, response_metadata: {} } });
    }
    if (path.endsWith("/requests/active-delete-request")) return json(route, { detail: "fixture_waiting" }, 503);
    if (path.endsWith("/requests/synthetic-evidence/evidence")) return json(route, {
      schema_version: "world-chat-evidence.v1", request_id: "synthetic-evidence", route: "synthetic-read-only",
      retrieval_outcome: "found", capability: "available",
      items: [0, 1].map(index => ({ reference: `synthetic-evidence-${index}`, kind: "canonical_source", episode: null,
        label: `Synthetic source ${index + 1}`, excerpt: "Synthetic retained source excerpt. ".repeat(18),
        occurred_at: "2026-10-05T01:00:00Z", availability: "available", related_character: null, direction: null,
        canonical_href: `/worlds/${FEED_WORLD}/posts/synthetic-source-${index}` })),
    });
    if (path.endsWith("/diagnostics/requests")) return json(route, { world_id: FEED_WORLD, thread_id: SYNTHETIC_THREAD, items: [], next_cursor: null });
    if (path.endsWith("/diagnostics")) return json(route, { world_id: FEED_WORLD, thread_id: SYNTHETIC_THREAD,
      request_id: null, request_state: null, request: null, status: "not_recorded", details: null,
      record: state.longDiagnostics ? { version: "chat-retrieval-diagnostics.v1", events: Array.from({ length: 40 }, (_, i) => ({ event: "request", items: i, executed: true })), omitted_events: 0 } : null,
      capture: { enabled: false, remaining: 0, expires_at: null } });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
