import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Edge (Docker Compose): Caddy routes /api and /health to FastAPI, so no rewrites are needed.
// Dev (`pnpm dev`) and cloud demo (Vercel): set API_ORIGIN so the browser stays same-origin
// (cookies stay first-party and no CORS is needed). PLAN.md §3.2.
const apiOrigin = process.env.API_ORIGIN?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    if (!apiOrigin) return [];
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      { source: "/health", destination: `${apiOrigin}/health` },
    ];
  },
};

export default createNextIntlPlugin("./src/i18n/request.ts")(nextConfig);
