import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxy = {
  "/meta": "http://127.0.0.1:8000",
  "/recommendations": "http://127.0.0.1:8000",
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: apiProxy,
  },
  preview: { proxy: apiProxy },
});
