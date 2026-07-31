import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("lucide-react")) return "icons";
          if (id.includes("@radix-ui")) return "radix";
          if (id.includes("motion") || id.includes("framer-motion")) return "motion";
          if (id.includes("@tanstack")) return "query";
          if (id.includes("react")) return "react";
        },
      },
    },
  },
  server: {
    port: 3001,
    strictPort: true,
  },
});
