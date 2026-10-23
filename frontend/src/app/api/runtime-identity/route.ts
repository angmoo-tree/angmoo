import { version as productVersion } from "../../../../package.json";

// Public, content-free process identity for the local host launcher.
export async function GET() {
  const configuredVersion = process.env.ANGMOO_VERSION ?? productVersion;
  const currentVersion = new RegExp(`^${productVersion.replaceAll(".", "\\.")}(?:-dev(?:-[0-9a-f]{7,40})?)?$`);
  if (!currentVersion.test(configuredVersion)) {
    return Response.json({ error: "product_version_mismatch" }, {
      status: 503, headers: { "cache-control": "private, no-store" },
    });
  }
  return Response.json({
    version: productVersion,
    source_sha: /^[0-9a-f]{40}$/.test(process.env.ANGMOO_SOURCE_SHA ?? "") ? process.env.ANGMOO_SOURCE_SHA : "unknown",
    launch_id: /^[0-9a-f]{32}$/.test(process.env.ANGMOO_LAUNCH_ID ?? "") ? process.env.ANGMOO_LAUNCH_ID : "",
  }, { headers: { "cache-control": "private, no-store" } });
}
