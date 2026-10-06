/** Product route grammar shared by the toolbar, native client and static resolver. */
export function isSupportedProductRoute(route: string, options: { validateQuery?: boolean } = {}) {
  let url: URL;
  try { url = new URL(route, "http://angmoo.local"); } catch { return false; }
  if (!route.startsWith("/") || route.startsWith("//") || url.origin !== "http://angmoo.local" || url.hash) return false;
  if ([...url.searchParams.keys()].some(key => key.toLowerCase().startsWith("__angmoo_") || ["apikey", "launchtoken", "accesstoken"].includes(key.toLowerCase().replace(/[_-]/g, "")))) return false;
  if (url.pathname === "/memory-explorer") url.pathname = "/memory";
  if (url.pathname === "/worlds/new") url.pathname = "/studio/worlds/new";
  const creator = url.pathname.match(/^\/worlds\/([^/]+)\/creator$/);
  if (creator) url.pathname = `/studio/worlds/${creator[1]}`;
  const parts = url.pathname.split("/").filter(Boolean);
  const id = (value: string | undefined, encoded = true) => {
    if (!value) return false;
    try { const decoded = encoded ? decodeURIComponent(value) : value; return decoded.length <= 255 && !Array.from(decoded).some(ch => ch.charCodeAt(0) < 32 || ch === "/" || ch.charCodeAt(0) === 92) && decoded !== "." && decoded !== ".."; }
    catch { return false; }
  };
  const world = (value: string | undefined) => id(value) && decodeURIComponent(value!) !== "new";
  if (parts.length === 0) return true;
  if (parts[0] === "memory" && parts.length === 1) {
    if (options.validateQuery === false) return true;
    const seen = new Set<string>();
    for (const [key, value] of url.searchParams) {
      if (!["world", "subject", "memory"].includes(key) || seen.has(key) || !id(value, false)) return false;
      seen.add(key);
    }
    return (!seen.has("subject") || seen.has("world")) && (!seen.has("memory") || seen.has("subject"));
  }
  if (parts[0] === "studio") return parts.length === 1 || (parts.length === 2 && parts[1] === "import") || (parts.length === 3 && parts[1] === "worlds" && id(parts[2]));
  if (["settings", "login", "posts", "agents"].includes(parts[0])) return parts.length === 1 || (["posts", "agents"].includes(parts[0]) && parts.length === 2 && id(parts[1]));
  if (parts[0] === "worlds" && world(parts[1])) return parts.length === 2 || (parts.length === 3 && ["feed", "chat", "characters", "relationships"].includes(parts[2])) || (parts.length === 4 && ["posts", "chat", "characters"].includes(parts[2]) && id(parts[3]));
  if (parts.length === 5 && parts[0] === "characters" && id(parts[1]) && parts[2] === "worlds" && world(parts[3])) {
    if (parts[4] === "autonomy-setup") return true;
    if (parts[4] === "relationship-graph") return options.validateQuery === false || [...url.searchParams].every(([key, value]) => key === "provider" && value === "ladybug");
  }
  return false;
}
