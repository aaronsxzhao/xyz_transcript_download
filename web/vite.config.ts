import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// API port can be set via environment variable, defaults to 8000
const apiPort = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    manifest: 'manifest.json',
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // All page controllers are available together. Only optional rich
          // formatting and transcript virtualization need additional files.
          if (id.includes('/src/') && !/\/components\/(FormattedSummary|TranscriptSegments)\.|\/components\/video\/(MarkdownPreview|HighlightedCode|TranscriptPanel)\./.test(id)) return 'workspace'
          // Keep icon helpers with the icons: dozens of tiny shared icon chunks
          // add request waterfalls on high-latency routes to the server.
          if (id.includes('/node_modules/lucide-react/')) return 'workspace'
          // CommonJS/JSX helpers belong to the app runtime, otherwise Rollup
          // pulls the entire viewer dependency chunk into the initial page.
          if (id.includes('commonjsHelpers') || /\/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)) {
            return 'workspace'
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
        ws: true, // Enable WebSocket proxying
      },
      '/data': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
