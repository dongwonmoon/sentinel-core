import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: resolveApiTarget(mode),
        changeOrigin: true,
        secure: false,
      },
    },
  },
}));

function resolveApiTarget(mode: string): string {
  if (mode === "development") {
    return process.env?.VITE_API_BASE_URL || "http://localhost:8000";
  }
  return "http://localhost:8000";
}
