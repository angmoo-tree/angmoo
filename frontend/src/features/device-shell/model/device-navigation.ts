import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export type ProductWindowCapability = "memory" | "phone" | "relationship-graph" | "studio";
export type ProductRouteExposure =
  | "bottom-navigation"
  | "direct-only"
  | "external"
  | "hidden";

export type ProductRouteCapability = {
  canonicalRoute?: string;
  exposure: ProductRouteExposure;
  id: string;
  next: "supported";
  routeFamily: string;
  static: "supported" | "unsupported";
  window: ProductWindowCapability;
};

/**
 * Reviewed Local route matrix.  Only entries supported by both Next and the
 * static/Tauri composition can become Phone bottom-navigation destinations.
 * Hosted-only routes stay explicit and fail closed instead of leaking dead
 * links into the installed product.
 */
export const LOCAL_PRODUCT_ROUTE_CAPABILITIES = [
  {
    exposure: "direct-only",
    id: "memory",
    next: "supported",
    routeFamily: "/memory",
    static: "supported",
    window: "memory",
  },
  {
    exposure: "bottom-navigation",
    id: "home",
    next: "supported",
    routeFamily: PRODUCT_ROUTES.deviceHome,
    static: "supported",
    window: "phone",
  },
  {
    exposure: "bottom-navigation",
    id: "feed",
    next: "supported",
    routeFamily: "/posts",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "bottom-navigation",
    id: "agents",
    next: "supported",
    routeFamily: "/agents",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "bottom-navigation",
    id: "settings",
    next: "supported",
    routeFamily: PRODUCT_ROUTES.settings,
    static: "supported",
    window: "phone",
  },
  {
    exposure: "direct-only",
    id: "world-app",
    next: "supported",
    routeFamily: "/worlds/{worldId}",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "direct-only",
    id: "world-post-detail",
    next: "supported",
    routeFamily: "/worlds/{worldId}/posts/{postId}",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "direct-only",
    id: "world-chat-thread",
    next: "supported",
    routeFamily: "/worlds/{worldId}/chat/{threadId}",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "direct-only",
    id: "world-character-profile",
    next: "supported",
    routeFamily: "/worlds/{worldId}/characters/{worldCharacterId}",
    static: "supported",
    window: "phone",
  },
  {
    exposure: "direct-only",
    id: "creator-studio",
    next: "supported",
    routeFamily: "/studio",
    static: "supported",
    window: "studio",
  },
  {
    exposure: "direct-only",
    id: "relationship-graph",
    next: "supported",
    routeFamily: "/characters/{characterId}/worlds/{worldId}/relationship-graph",
    static: "supported",
    window: "relationship-graph",
  },
  {
    canonicalRoute: PRODUCT_ROUTES.studioNewWorld,
    exposure: "hidden",
    id: "legacy-world-create-alias",
    next: "supported",
    routeFamily: "/worlds/new",
    static: "supported",
    window: "studio",
  },
  {
    canonicalRoute: "/studio/worlds/{worldId}",
    exposure: "hidden",
    id: "legacy-world-creator-alias",
    next: "supported",
    routeFamily: "/worlds/{worldId}/creator",
    static: "supported",
    window: "studio",
  },
  ...[
    "/search",
    "/notifications",
    "/messages",
    "/profiles",
    "/tree",
    "/licenses",
    "/angmoo-api",
  ].map(
    (routeFamily): ProductRouteCapability => ({
      exposure: "hidden",
      id: `next-only-${routeFamily.slice(1)}`,
      next: "supported",
      routeFamily,
      static: "unsupported",
      window: "phone",
    }),
  ),
] satisfies ProductRouteCapability[];

export type LocalDeviceNavigationId = "agents" | "feed" | "home" | "settings";

export const LOCAL_DEVICE_NAVIGATION = LOCAL_PRODUCT_ROUTE_CAPABILITIES.filter(
  (capability) => capability.exposure === "bottom-navigation",
).map((capability) => ({
  href: capability.routeFamily,
  id: capability.id as LocalDeviceNavigationId,
}));

const STATIC_PRODUCT_ROUTE_PATTERNS = [
  /^\/$/,
  /^\/login$/,
  /^\/settings$/,
  /^\/memory$/,
  /^\/memory-explorer$/,
  /^\/posts(?:\/[^/]+)?$/,
  /^\/agents(?:\/new|\/[^/]+)?$/,
  /^\/studio$/,
  /^\/studio\/import$/,
  /^\/studio\/worlds\/(?:new|[^/]+)$/,
  /^\/worlds\/new$/,
  /^\/worlds\/[^/]+\/creator$/,
  /^\/worlds\/(?!new(?:\/|$))[^/]+(?:\/(?:feed|chat|characters|relationships))?$/,
  /^\/worlds\/(?!new(?:\/|$))[^/]+\/chat\/[^/]+$/,
  /^\/worlds\/(?!new(?:\/|$))[^/]+\/characters\/[^/]+$/,
  /^\/worlds\/(?!new(?:\/|$))[^/]+\/posts\/[^/]+$/,
  /^\/characters\/[^/]+\/worlds\/(?!new(?:\/|$))[^/]+\/(?:autonomy-setup|relationship-graph)$/,
] as const;

function localProductPathname(href: string): string | null {
  try {
    const parsed = new URL(href, "http://angmoo.local");
    if (parsed.origin !== "http://angmoo.local") return null;
    return parsed.pathname.replace(/\/+$/, "") || "/";
  } catch {
    return null;
  }
}

/**
 * Fail-closed static/Tauri product-route check. Next may keep hosted-only
 * pages, but the installed product must never expose a control that opens a
 * route the static router cannot render.
 */
export function isStaticLocalProductRouteSupported(href: string): boolean {
  const pathname = localProductPathname(href);
  return Boolean(
    pathname && STATIC_PRODUCT_ROUTE_PATTERNS.some((pattern) => pattern.test(pathname)),
  );
}

export function activeLocalDeviceNavigation(
  pathname: string | null,
): LocalDeviceNavigationId | null {
  if (!pathname) return null;
  if (pathname === PRODUCT_ROUTES.deviceHome) return "home";
  if (pathname === "/posts" || pathname.startsWith("/posts/")) return "feed";
  if (
    pathname === "/agents" ||
    pathname.startsWith("/agents/") ||
    /^\/characters\/[^/]+\/worlds\/[^/]+\/autonomy-setup$/.test(pathname)
  ) {
    return "agents";
  }
  if (pathname === PRODUCT_ROUTES.settings) return "settings";
  return null;
}
