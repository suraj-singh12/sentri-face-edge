import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/media": "http://127.0.0.1:8765"
    }
  },
  build: {
    outDir: "../src/sentriface/ui_static",
    emptyOutDir: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "vendor-react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            { name: "vendor-mantine", test: /node_modules[\\/]@mantine[\\/]/ },
            { name: "vendor-icons", test: /node_modules[\\/]@tabler[\\/]/ },
            { name: "world", test: /src[\\/](views[\\/](World|ClusterDrilldown)[^\\/]*|utils[\\/]world|hooks[\\/]useWorldController)/ }
          ]
        }
      }
    }
  }
});
