// Public, content-free process identity for the local host launcher.
export async function GET() {
  return Response.json({
    version: process.env.ANGMOO_VERSION ?? "0.1.0",
    source_sha: /^[0-9a-f]{40}$/.test(process.env.ANGMOO_SOURCE_SHA ?? "") ? process.env.ANGMOO_SOURCE_SHA : "unknown",
    launch_id: /^[0-9a-f]{32}$/.test(process.env.ANGMOO_LAUNCH_ID ?? "") ? process.env.ANGMOO_LAUNCH_ID : "",
  }, { headers: { "cache-control": "private, no-store" } });
}
