import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Remind about published security advisories (Next.js 16.4.3 -> 16.4.6 was one).
    agentUpgrade: "security",
  },
  // Phase 1 served the app under /studio; keep those URLs working.
  async redirects() {
    return [
      { source: "/studio", destination: "/dashboard", permanent: true },
      { source: "/studio/:path*", destination: "/:path*", permanent: true },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
