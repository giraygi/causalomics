import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Vite server proxies /api to the backend container
// (published on localhost:8001 by docker compose). In production nginx does this.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
});
