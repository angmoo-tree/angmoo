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
const developmentScriptSources =
  process.env.NODE_ENV === "development" ? ["'unsafe-eval'"] : [];

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  [
    "script-src 'self' 'unsafe-inline'",
    ...developmentScriptSources,
    "https://accounts.google.com",
    "https://challenges.cloudflare.com",
  ].join(" "),
  "style-src 'self' 'unsafe-inline' https://accounts.google.com",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://accounts.google.com https://challenges.cloudflare.com",
  "frame-src https://accounts.google.com https://challenges.cloudflare.com",
  "worker-src 'self' blob:",
].join("; ");

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy,
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
