import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // The e2e run uses its own build folder so it never disturbs a running dev server.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
