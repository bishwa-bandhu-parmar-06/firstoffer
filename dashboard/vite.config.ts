import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs separately (uvicorn on :8000); forward its paths to it.
// (/job/123 share pages are left to Vite's own page fallback in development.)
const API_PATHS = ["/jobs", "/filters", "/companies", "/stats", "/sources", "/health", "/site", "/sitemap.xml", "/robots.txt"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, "http://127.0.0.1:8000"])),
  },
});
