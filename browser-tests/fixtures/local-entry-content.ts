import type { Page, Route } from "@playwright/test";
import { uiDManualPost } from "../continuity-next-fixture";

/** Synthetic content boundary only. Identity, environment, registration and
 * credentials continue through the real disposable HTTP backend. Domain
 * receipt/index persistence is verified by test_stability_memory_integration. */
export async function installLocalContent(page: Page, ids: {
  owner: string; world: string; profile: string; character: string; actor: string;
}) {
  const threadId = "synthetic-entry-chat";
  const role = (owner: boolean) => ({ world_character_id: owner ? ids.profile : ids.actor,
    character_id: owner ? `owner-${ids.profile}` : ids.character, display_name: owner ? "User" : "Synthetic Ian",
    handle: owner ? "synthetic_user" : "synthetic_ian", avatar_url: null, banner_url: null,
    role_key: null, control_mode: owner ? "owner_controlled" : "autonomous", profile_capability: "available" });
  const message = (id: number, own: boolean, content: string) => ({ id, thread_id: threadId,
    role: own ? "user" : "assistant", status: "ok", sender_user_id: own ? ids.owner : null,
    sender_character_id: own ? null : ids.character, content, created_at: "2026-10-19T10:00:00Z", attachment: null });
  const thread = { id: threadId, world_id: ids.world, requester: role(true), responding: role(false),
    selected_model: "gemini-3.1-flash-lite", selected_thinking_level: "medium", default_model: "gemini-3.1-flash-lite",
    default_thinking_level: "medium", model_binding_mode: "default", last_message_at: null, latest_message: null,
    created_at: "2026-10-19T10:00:00Z", messages: [] as ReturnType<typeof message>[],
    evidence_summaries: [] as { request_id: string; assistant_message_id: number; capability: string; count: number }[] };
  const text = "Ian described the pine trail plan after reading the earlier hiking note.";
  const segments = [{ key: "kind", text: "오늘 SNS 활동 종류: " }, { key: null, text: "posts_authored | " },
    { key: "actor", text: "행동 주체: " }, { key: null, text: "Synthetic Ian | " }, { key: "body", text: "내용: " }, { key: null, text }];
  const post = { ...uiDManualPost({ id: "synthetic-pine-post", title: "Pine trail plan", body: text, worldId: ids.world }),
    author_world_character_id: ids.actor, author_character_id: ids.character, author_name: "Synthetic Ian", author_avatar_url: null,
    can_owner_like: false, can_owner_reply: false, viewer_like_state: "unavailable", media: [] };
  const fixture = { sends: 0, streams: 0, evidenceReads: 0 };
  let accepted: Record<string, unknown> | null = null;
  const handler = async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (!path.startsWith(`/worlds/${ids.world}/`)) return route.fallback();
    if (path.endsWith("/manual-social/feed")) return route.fulfill({ json: { schema_version: "owner-manual-social-v1",
      world_id: ids.world, owner_world_character_id: ids.profile, items: [post] } });
    const chatBase = `/worlds/${ids.world}/chat/threads/${threadId}`;
    if (path === chatBase) return route.fulfill({ json: thread });
    if (path.endsWith("/requests/latest")) return route.fulfill({ json: { response_request: accepted } });
    if (path.endsWith("/messages") && request.method() === "POST") {
      fixture.sends++;
      const user = message(1, true, request.postDataJSON().content); thread.messages.push(user);
      accepted = { protocol_version: "chat-generation-stream.v1", request_id: "synthetic-entry-request",
        request_scope_hash: "a".repeat(64), generation_id: "synthetic-entry-generation", attempt_number: 1,
        response_slot_id: "synthetic-entry-slot", state: "accepted", route: null, retryable: false, failure_class: null,
        last_accepted_sequence: -1, user_message: user, assistant_message: null, response_metadata: {} };
      return route.fulfill({ json: { outcome: "accepted", user_message: user, response_request: accepted } });
    }
    if (path.endsWith("/requests/synthetic-entry-request/events")) {
      fixture.streams++;
      const assistant = message(2, false, "I remember our plan to walk the pine trail.");
      thread.messages.push(assistant);
      thread.evidence_summaries = [{ request_id: "synthetic-entry-request", assistant_message_id: 2, capability: "available", count: 2 }];
      const events = [{ type: "accepted", payload: {} }, { type: "delta", payload: { text: assistant.content } }, { type: "completed", payload: {} }]
        .map((value, sequence) => ({ ...accepted, ...value, sequence }));
      accepted = { ...accepted, state: "committed", assistant_message: assistant, last_accepted_sequence: 2 };
      return route.fulfill({ contentType: "application/x-ndjson", body: events.map(e => JSON.stringify(e)).join("\n") + "\n" });
    }
    if (path.endsWith("/requests/synthetic-entry-request")) return route.fulfill({ json: accepted });
    if (path.endsWith("/requests/synthetic-entry-request/evidence")) {
      fixture.evidenceReads++;
      const item = { reference: "synthetic:sns", kind: "today_sns_activity", label: "오늘 SNS 활동", availability: "available",
        excerpt: segments.map(s => s.text).join(""), display_segments: segments, occurred_at: "2026-10-19T10:00:00Z",
        related_character: "Synthetic Ian", direction: null, canonical_href: null, episode: null };
      return route.fulfill({ json: { schema_version: "world-chat-evidence.v1", request_id: "synthetic-entry-request",
        route: "canonical", retrieval_outcome: "found", capability: "available", items: [item,
          { ...item, reference: "synthetic:memory", kind: "episode_memory", label: "Pine trail discussion", excerpt: text, display_segments: null }],
        current_context: [], retrieval_limitations: { partial_axes: [], degraded_reason: null }, read_limitations: [] } });
    }
    if (path.includes("/diagnostics")) return route.fulfill({ json: { world_id: ids.world, thread_id: threadId,
      status: "not_recorded", request: null, record: null, capture: { enabled: false, remaining: 0, expires_at: null }, items: [] } });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:3492/api/v1/**", handler);
  return { fixture, threadId, text };
}
