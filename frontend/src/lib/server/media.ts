import { getBackendBaseUrl } from "./backend";

// Backend owns public-media and World authorization. This transport never
// mounts private storage or accepts a client-selected upstream.
export async function proxyMedia(request: Request, path: string[]) {
  if (!path.length || path.some((part) => !part || part === "." || part === ".." || /[/\\%\u0000-\u001f\u007f]/.test(part))) {
    return new Response(null, { status: 400 });
  }
  const headers = new Headers({ "accept-encoding": "identity" });
  for (const name of ["accept", "range", "if-range", "if-none-match", "if-modified-since"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const cookies = (request.headers.get("cookie") ?? "").split(";").map((v) => v.trim())
    .filter((v) => v.startsWith("angmoo_browser_session="));
  if (cookies.length) headers.set("cookie", cookies.join("; "));
  const upstream = await fetch(`${getBackendBaseUrl()}/media/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`, {
    method: request.method, headers, signal: request.signal, cache: "no-store", redirect: "manual",
  });
  // Do not follow redirects with the session cookie, or disclose internal URLs.
  if (upstream.status >= 300 && upstream.status < 400 && upstream.status !== 304) {
    await upstream.body?.cancel();
    return new Response(null, { status: 502 });
  }
  const forwarded = new Headers({ "x-content-type-options": "nosniff" });
  for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "cache-control", "etag", "last-modified", "content-disposition", "vary"]) {
    const value = upstream.headers.get(name);
    if (value !== null) forwarded.set(name, value);
  }
  if (!forwarded.has("cache-control")) forwarded.set("cache-control", "private, no-store");
  // fetch decompresses encoded bodies; their original length is no longer valid.
  if (upstream.headers.has("content-encoding")) forwarded.delete("content-length");
  return new Response(request.method === "HEAD" || [204, 205, 304].includes(upstream.status) ? null : upstream.body, {
    status: upstream.status, headers: forwarded,
  });
}
