import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5184,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: "ws", host, port: 5185 } : undefined,
    watch: {
      ignored: ["**/src-tauri/**", "**/dist/**"],
    },
  },
});
