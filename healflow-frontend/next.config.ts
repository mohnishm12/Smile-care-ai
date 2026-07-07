import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required by Dockerfile.frontend — produces .next/standalone server bundle
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
