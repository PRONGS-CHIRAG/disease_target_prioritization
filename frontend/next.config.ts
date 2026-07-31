import path from "node:path";

import type { NextConfig } from "next";

// Static export (milestone5_plan.md §2.2) and rewrites cannot both be
// active: the static-export guide vendored in this Next.js version
// (frontend/AGENTS.md points at node_modules/next/dist/docs) lists
// Rewrites under "Unsupported Features," and Next enforces that for
// `next dev` too whenever `output: "export"` is set, not only for
// `next build`. `BUILD_STATIC_EXPORT=1` is set by `make frontend-build`
// and the Dockerfile (never by `next dev`), so dev keeps its API proxy and
// the production build gets its static export from the same config file.
const isStaticExport = process.env.BUILD_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  // An unrelated lockfile at the user's home directory otherwise makes
  // Turbopack guess the workspace root incorrectly.
  turbopack: { root: path.join(__dirname) },
  output: isStaticExport ? "export" : undefined,
  ...(isStaticExport
    ? {}
    : {
        async rewrites() {
          // Same-origin in dev: the browser only ever talks to :3000, so no
          // CORS is needed (milestone5_plan.md §4.5). The FastAPI backend
          // is expected on :8000 — override with DTP_API_ORIGIN if it runs
          // elsewhere.
          const apiOrigin = process.env.DTP_API_ORIGIN ?? "http://localhost:8000";
          return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
        },
      }),
};

export default nextConfig;
