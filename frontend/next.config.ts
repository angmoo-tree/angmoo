import type { NextConfig } from "next";

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

const backendBaseUrl = (process.env.ANGMOO_API_BASE_URL ?? "http://127.0.0.1:8080").replace(
  /\/$/,
  "",
);

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/security.txt",
        destination: "/.well-known/security.txt",
        permanent: true,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/media/:path*",
        destination: `${backendBaseUrl}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
