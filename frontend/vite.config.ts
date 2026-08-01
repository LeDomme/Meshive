import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  publicDir: "../resources",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
})
