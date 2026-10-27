import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The production build is written into the Python package so the backend can serve it
// (users never need Node.js to run the app).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../backend/paperlook/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 2000,
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
