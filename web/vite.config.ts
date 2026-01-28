import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// API port can be set via environment variable, defaults to 8000
const apiPort = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    // Ensure clean output
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
      '/data': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
