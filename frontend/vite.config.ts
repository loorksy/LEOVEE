import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    headers: {
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      // No Content-Security-Policy here: the dev server isn't the security
      // boundary (docker/caddy/Caddyfile.prod is, and enforces script-src
      // 'self' with no 'unsafe-inline' for real) — Vite's own HMR client
      // injects an inline module script into every page it serves, so
      // mirroring that policy here doesn't test anything, it just breaks the
      // dev server in any CSP-enforcing browser (confirmed: React Refresh's
      // preamble is blocked and the app never mounts). Application code stays
      // CSP-clean regardless — see public/theme-boot.js for why the one
      // script this app needs before first paint is an external file, not
      // inline — so the real policy is exercised unchanged in production.
    },
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
