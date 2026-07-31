import react from "@vitejs/plugin-react-swc";
import path from "path";
import { defineConfig } from "vite";

// The port is load-bearing: the backend's CORS allow-list names 3000.
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 3000,
    hmr: { overlay: false },
  },
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    // Every browser that supports the APIs this app uses (IntersectionObserver,
    // dynamic import) is well past es2020, so don't ship transpiler output for
    // engines that will never load it.
    target: "es2020",
    cssMinify: true,
    // One page, one route: the only worthwhile split is the watchlist editor,
    // which React.lazy already carves out. Manual vendor chunks would just add
    // a second blocking request for code the first paint needs anyway.
    reportCompressedSize: true,
  },
});
