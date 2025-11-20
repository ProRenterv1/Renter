import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: [".js", ".jsx", ".ts", ".tsx", ".json"],
    alias: {
      "vaul@1.1.2": "vaul",
      "sonner@2.0.3": "sonner",
      "recharts@2.15.2": "recharts",
      "react-resizable-panels@2.1.7": "react-resizable-panels",
      "react-hook-form@7.55.0": "react-hook-form",
      "react-day-picker@8.10.1": "react-day-picker",
      "@radix-ui/react-slot@1.1.2": "@radix-ui/react-slot",
      "@radix-ui/react-aspect-ratio@1.1.2": "@radix-ui/react-aspect-ratio",
      "@radix-ui/react-alert-dialog@1.1.6": "@radix-ui/react-alert-dialog",
      "@radix-ui/react-accordion@1.2.3": "@radix-ui/react-accordion",
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: { target: "esnext", outDir: "build" },
  server: {
    port: 3000,
    open: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
