import type { NextConfig } from "next";

if (process.env.NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE !== "tauri-static") {
  throw new Error("The static shell must be built with the tauri-static profile.");
}

const nextConfig: NextConfig = {
  images: { unoptimized: true },
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
