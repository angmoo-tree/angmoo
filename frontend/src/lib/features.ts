export const EXPERIMENTAL_IMAGE_ENABLED =
  process.env.NEXT_PUBLIC_EXPERIMENTAL_IMAGE_ENABLED === "true";

export const PRIVATE_ADMIN_ENABLED =
  process.env.NEXT_PUBLIC_PRIVATE_ADMIN_ENABLED === "true";

export type HostedNavigationId = "admin";

export type HostedNavigationItem = Readonly<{
  id: HostedNavigationId;
  name: string;
  href: string;
}>;

export type HostedFrontendExtension = Readonly<{
  navigationItems: readonly HostedNavigationItem[];
  routeCapabilities: readonly HostedNavigationId[];
}>;

const HOSTED_NAVIGATION_REGISTRY: Record<
  HostedNavigationId,
  HostedNavigationItem
> = {
  admin: {
    id: "admin",
    name: "어드민",
    href: "/admin",
  },
};

function hostedNavigationIds(): HostedNavigationId[] {
  const configured = process.env.NEXT_PUBLIC_HOSTED_FRONTEND_ROUTES;
  const values = configured
    ? configured
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean)
    : PRIVATE_ADMIN_ENABLED
      ? ["admin"]
      : [];

  const unique = new Set(values);
  if (unique.size !== values.length) {
    throw new Error("Duplicate hosted frontend route capability");
  }
  for (const value of values) {
    if (!(value in HOSTED_NAVIGATION_REGISTRY)) {
      throw new Error(`Unknown hosted frontend route capability: ${value}`);
    }
  }
  return values as HostedNavigationId[];
}

const hostedIds = hostedNavigationIds();

export const HOSTED_FRONTEND_EXTENSION: HostedFrontendExtension = {
  navigationItems: hostedIds.map((id) => HOSTED_NAVIGATION_REGISTRY[id]),
  routeCapabilities: hostedIds,
};

export function hasHostedFrontendCapability(
  capability: HostedNavigationId,
): boolean {
  return HOSTED_FRONTEND_EXTENSION.routeCapabilities.includes(capability);
}
