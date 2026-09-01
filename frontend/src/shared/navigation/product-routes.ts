export const PRODUCT_ROUTES = {
  deviceHome: "/",
  settings: "/settings",
  studio: "/studio",
  studioImport: "/studio/import",
  studioNewWorld: "/studio/worlds/new",
} as const;

export type ProductRouteSearchParams = Readonly<
  Record<string, string | string[] | undefined>
>;

export function productRouteWithSearchParams(
  pathname: string,
  searchParams: ProductRouteSearchParams,
): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        query.append(key, item);
      }
      continue;
    }

    if (value !== undefined) {
      query.append(key, value);
    }
  }

  const serialized = query.toString();
  return serialized ? `${pathname}?${serialized}` : pathname;
}

export function worldAppRoute(worldId: string): string {
  return `/worlds/${encodeURIComponent(worldId)}`;
}

export function worldPostDetailRoute(worldId: string, postId: string): string {
  return `${worldAppRoute(worldId)}/posts/${encodeURIComponent(postId)}`;
}

export function worldChatRoute(worldId: string): string {
  return `${worldAppRoute(worldId)}/chat`;
}

export function worldChatThreadRoute(worldId: string, threadId: string): string {
  return `${worldChatRoute(worldId)}/${encodeURIComponent(threadId)}`;
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
