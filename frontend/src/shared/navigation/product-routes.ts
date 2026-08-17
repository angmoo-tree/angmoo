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

export function studioWorldRoute(worldId: string): string {
  return `/studio/worlds/${encodeURIComponent(worldId)}`;
}
