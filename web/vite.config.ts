import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), "VITE_"), ...process.env };
  const api = new URL(env.VITE_API_BASE || "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(api.protocol)) throw new Error("VITE_API_BASE must use HTTP or HTTPS.");
  const socketOrigin = api.origin.replace(/^http/, "ws");
  return {
  base: process.env.VITE_BASE || "/",
  plugins: [react(), {
    name: "clear-api-csp",
    transformIndexHtml(html) {
      return html.replace("connect-src 'self'", `connect-src 'self' ${api.origin} ${socketOrigin}`);
    }
  }],
  build: {
    modulePreload: {
      resolveDependencies(_filename, deps) {
        return deps.filter((dep) => {
          const normalized = dep.replace(/\\/g, "/");
          return !/(^|\/)(globe|maplibre|leaflet|markdown|plotly)-/.test(normalized);
        });
      }
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }
          if (
            id.includes("plotly.js-dist-min") ||
            id.includes("react-plotly.js")
          ) {
            return "plotly";
          }
          if (
            id.includes("@react-three/") ||
            id.includes("\\three\\") ||
            id.includes("/three/") ||
            id.includes("postprocessing")
          ) {
            return "globe";
          }
          if (id.includes("maplibre-gl")) {
            return "maplibre";
          }
          if (id.includes("leaflet")) {
            return "leaflet";
          }
          if (id.includes("recharts")) {
            return "charts";
          }
          if (
            id.includes("react-markdown") ||
            id.includes("remark-gfm") ||
            id.includes("/remark-") ||
            id.includes("\\remark-") ||
            id.includes("/mdast-") ||
            id.includes("\\mdast-") ||
            id.includes("/hast-") ||
            id.includes("\\hast-") ||
            id.includes("/micromark") ||
            id.includes("\\micromark") ||
            id.includes("/unist-") ||
            id.includes("\\unist-")
          ) {
            return "markdown";
          }
          if (
            id.includes("react-router") ||
            id.includes("\\react\\") ||
            id.includes("/react/") ||
            id.includes("scheduler")
          ) {
            return "react-vendor";
          }
          return "vendor";
        }
      }
    }
  },
  server: {
    port: 5173
  }
  };
});
