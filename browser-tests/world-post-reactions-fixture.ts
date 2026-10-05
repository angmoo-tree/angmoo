import type { Page, Route } from "@playwright/test";
import { installSocialChatFixture, SYNTHETIC_ROOT } from "./world-social-chat-fixture";
import { FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installWorldCharacterManagementRoutes } from "./world-character-management-fixture";

export async function installPostReactionFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const base = await installSocialChatFixture(page, isStatic, baseURL, language);
  await installWorldCharacterManagementRoutes(page);
  const state = { base, gets: [] as { path: string; cursor: string | null }[], events: [] as unknown[],
    getDelay: 0, profileFailure: 0, likeFailure: 0, corruptLike: false, loseLikeResponse: false, likeDelay: 0, likeCount: 19,
    profileCounts: { post_count: 61, reply_count: 73, liked_post_count: 30, received_like_count: 89 },
    otherLikes: new Set<string>(), requestCount: 0 };
  for (let index = 0; index < 30; index++) base.posts.push({ ...base.posts[0], id: `paged-${index}`, title: `Synthetic page ${index}`,
    body: `Original synthetic page ${index} ` + "Long content ".repeat(35), author_world_character_id: "synthetic-responder", viewer_like_state: "liked", reply_to_post_id: null });
  for (const post of base.posts.filter(post => post.id.startsWith("paged-"))) state.otherLikes.add(post.id);
  await page.addInitScript(() => {
    Object.assign(window, { __reactionEvents: [] });
    window.addEventListener("angmoo-social-reaction", event => (window as unknown as { __reactionEvents: unknown[] }).__reactionEvents.push((event as CustomEvent).detail));
  });
  const globalPost = (post: typeof base.posts[number]) => ({ ...post, author_user_id: null, author_character_id: `character-${post.author_world_character_id}`,
    comment_count: 0, repost_count: 0, quote_count: 0, quote_post_id: null, repost_of_post_id: null, quoted_post: null, reposted_post: null,
    report_hidden: false, info_kind: null, source_name: null, source_url: null, location_label: null, observed_at: null, mentioned_characters: [] });
  const respond = async (route: Route, json: unknown, status = 200) => {
    if (state.getDelay && route.request().method() === "GET") await new Promise(resolve => setTimeout(resolve, state.getDelay));
    return route.fulfill({ status, json });
  };
  const handler = async (route: Route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (path === "/auth/me" && state.profileFailure === 401) return respond(route, { detail: "session_expired" }, 401);
    const like = path.match(/\/manual-social\/posts\/([^/]+)\/like$/);
    if (like) {
      state.requestCount++;
      base.writes.push({ path, method, key: request.headers()["idempotency-key"], data: {} });
      if (state.likeDelay) await new Promise(resolve => setTimeout(resolve, state.likeDelay));
      if (state.likeFailure) return respond(route, { detail: "like_unavailable" }, state.likeFailure);
      const post = base.posts.find(post => post.id === like[1])!;
      post.viewer_like_state = method === "PUT" ? "liked" : "not_liked"; post.like_count = state.likeCount;
      if (state.loseLikeResponse) return route.abort("failed");
      return respond(route, { world_id: state.corruptLike ? "forged-world" : FEED_WORLD, post_id: post.id, owner_world_character_id: ownerId(),
        viewer_like_state: post.viewer_like_state, like_count: post.like_count, can_owner_like: true });
    }
    if (path === `/worlds/${FEED_WORLD}/manual-social/feed`) {
      state.gets.push({ path, cursor: null });
      return respond(route, { schema_version: "owner-manual-social-v1", world_id: FEED_WORLD, owner_world_character_id: ownerId(), items: base.posts.map(post => ({ ...post })) });
    }
    const manualDetail = path.match(/\/manual-social\/posts\/([^/]+)$/);
    if (manualDetail) {
      state.gets.push({ path, cursor: url.searchParams.get("offset") });
      const selected = base.posts.find(post => post.id === manualDetail[1]);
      if (!selected) return respond(route, { detail: "post_not_in_world" }, 404);
      const descendants = (id: string): typeof base.posts => base.posts.filter(post => post.reply_to_post_id === id).flatMap(post => [post, ...descendants(post.id)]);
      const children = descendants(selected.id), offset = Number(url.searchParams.get("offset") ?? 0);
      const parents = [...new Set([selected, ...children.slice(offset, offset + 50)].map(post => post.reply_to_post_id).filter(Boolean))].map(id => ({ post_id: id, state: "available" }));
      return respond(route, { schema_version: "owner-manual-social-thread-v2", world_id: FEED_WORLD, owner_world_character_id: ownerId(), root_post_id: SYNTHETIC_ROOT,
        selected_post: { ...selected, reply_count: children.length }, parent: parents.find(parent => parent.post_id === selected.reply_to_post_id) ?? null,
        parent_references: parents, replies: children.slice(offset, offset + 50).map(post => ({ ...post, reply_count: descendants(post.id).length })),
        page_offset: offset, next_offset: offset + 50 < children.length ? offset + 50 : null });
    }
    const profile = path.match(/\/world-characters\/([^/]+)\/social-profile$/);
    if (profile) {
      const tab = url.searchParams.get("tab"), cursor = url.searchParams.get("cursor"), offset = Number(cursor ?? 0);
      state.gets.push({ path, cursor });
      if (state.profileFailure) return respond(route, { detail: "profile_unavailable" }, state.profileFailure);
      const rows = tab === "likes" ? base.posts.filter(post => profile[1] === ownerId() ? post.viewer_like_state === "liked" : state.otherLikes.has(post.id))
        : base.posts.filter(post => post.author_world_character_id === profile[1] && (tab === "replies" ? Boolean(post.reply_to_post_id) : !post.reply_to_post_id));
      const items = rows.slice(offset, offset + 10).map(post => ({ ...post, mentioned_characters: [], media: post.media }));
      return respond(route, { schema_version: "world-character-social-profile-v1", world_id: FEED_WORLD, world_character_id: profile[1],
        character_id: `character-${profile[1]}`, tab, counts: { ...state.profileCounts }, items, next_cursor: offset + 10 < rows.length ? String(offset + 10) : null });
    }
    if (path === "/feed") {
      const cursor = url.searchParams.get("cursor"), offset = Number(cursor ?? 0);
      state.gets.push({ path, cursor });
      const rows = base.posts.filter(post => post.id.startsWith("paged-"));
      return respond(route, { items: rows.slice(offset, offset + 10).map(globalPost), next_cursor: offset + 10 < rows.length ? String(offset + 10) : null });
    }
    const globalDetail = path.match(/^\/posts\/([^/]+)\/thread$/);
    if (globalDetail) {
      state.gets.push({ path, cursor: null });
      const root = base.posts.find(post => post.id === globalDetail[1]) ?? base.posts.find(post => post.id === SYNTHETIC_ROOT)!;
      return respond(route, { post: { ...globalPost(root), comments: [] }, replies: base.posts.filter(post => post.reply_to_post_id === root.id).map(globalPost) });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}
