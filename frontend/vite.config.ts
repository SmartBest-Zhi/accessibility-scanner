import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { ViteAliases } from 'vite-aliases';
// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    ViteAliases(),
  ],
  base:"./",
  server:{
    host: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  }
})
