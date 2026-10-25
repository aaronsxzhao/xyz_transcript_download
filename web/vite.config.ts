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
        strictExecutionOrder: true,
        codeSplitting: {
          // Keep every page controller (including Settings) in the document.
          // Only explicit tools may require another request.
          includeDependenciesRecursively: false,
          groups: [
            {name:'VideoCreation',priority:20,test:/\/src\/components\/video\/(VideoNoteForm|YouTubeCookieGuide)\./},
            {name:'workspace',priority:10,test:(id) => {
              if(id.includes('/src/') && !/\/lib\/(taskActions|notionExport|podcastPrint|videoPrint|mindmapCache|mindmapOutline|bilibiliFavorites|markdownDownload|legacyModelOptions)\./.test(id) && !/\/components\/(ArticleNote|CustomModelFields|DashboardDialog|ReaderAppearance|RegenerateDialog|PodcastNotionExport|ProcessingPanel|FormattedSummary|TranscriptSegments|ScreenshotGallery|PerformancePanel|DataRecovery|TranscriptMaintenance|LocalPodcastUpload|PodcastUploadForm)\.|\/components\/video\/(ReaderDetails|MindMapView|MarkdownPreview|HighlightedCode|TranscriptPanel|VideoNoteForm|YouTubeCookieGuide|BilibiliFavorites)\./.test(id)) return true
              return id.includes('/node_modules/lucide-react/') || id.includes('commonjsHelpers') || /\/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)
            }},
          ],
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
