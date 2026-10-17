import type { NextConfig } from "next";
import path from "node:path";

const hostedFrontendRoutes = (
  process.env.NEXT_PUBLIC_HOSTED_FRONTEND_ROUTES ?? ""
)
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const allowedHostedFrontendRoutes = new Set(["admin"]);

if (new Set(hostedFrontendRoutes).size !== hostedFrontendRoutes.length) {
  throw new Error("Duplicate hosted frontend route capability");
}
for (const route of hostedFrontendRoutes) {
  if (!allowedHostedFrontendRoutes.has(route)) {
    throw new Error(`Unknown hosted frontend route capability: ${route}`);
  }
}

const nextConfig: NextConfig = {
  // Isolate contributor previews/builds from an existing local server.
  distDir: process.env.ANGMOO_NEXT_DIST_DIR ?? ".next",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  output: "standalone",
  outputFileTracingRoot:path.join(process.cwd(),".."),
  outputFileTracingIncludes:{"/angmoo-api":["../docs/agent_guide.md","../docs/agent_guide.en.md"],"/agent_guide.md":["../docs/agent_guide.md","../docs/agent_guide.en.md"]},
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          {
            key: "Cache-Control",
            value: "no-cache, no-store, must-revalidate",
          },
          {
            key: "Service-Worker-Allowed",
            value: "/",
          },
        ],
      },
      {
        source: "/:path*",
        headers: [
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
        ],
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/security.txt",
        destination: "/.well-known/security.txt",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
