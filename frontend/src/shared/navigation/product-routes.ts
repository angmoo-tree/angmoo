export const PRODUCT_ROUTES = {
  deviceHome: "/",
  settings: "/settings",
  studio: "/studio",
  studioImport: "/studio/import",
  studioNewWorld: "/studio/worlds/new",
} as const;

export function worldAppRoute(worldId: string): string {
  return `/worlds/${encodeURIComponent(worldId)}`;
}

export function worldPostDetailRoute(worldId: string, postId: string): string {
  return `${worldAppRoute(worldId)}/posts/${encodeURIComponent(postId)}`;
}

export function studioWorldRoute(worldId: string): string {
  return `/studio/worlds/${encodeURIComponent(worldId)}`;
}

export function relationshipGraphRoute(
  characterId: string,
  worldId: string,
): string {
  return `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/relationship-graph`;
}
