import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/cameras": {
        target: process.env.VITE_CAMERA_PROXY_TARGET ?? "http://localhost:8090",
        changeOrigin: true,
      },
    },
  },
});
