import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// LOCAL-ONLY deployment helper (never part of the hosted app build). Serves deploy.html on 127.0.0.1:5174.
export default defineConfig({
  plugins: [react()],
  define: { global: "globalThis" },
  server: { host: "127.0.0.1", port: 5174, strictPort: true, open: "/deploy.html", fs: { allow: [resolve(__dirname, "..")] } },
});
