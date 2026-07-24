import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Let the SPA handle page-load requests (e.g. hard refresh on /intake)
// while still proxying XHR/fetch API calls to the backend.
function spaBypass(req) {
  const accept = req.headers?.accept || ''
  if (accept.includes('text/html')) {
    return req.url
  }
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/vcf': {
        target: 'http://localhost:5003',
        changeOrigin: true
      },
      '/auth': {
        target: 'http://localhost:5003',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      },
      '/cases': {
        target: 'http://localhost:5003',
        changeOrigin: true
      },
      '/intake': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/dashboard': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/communications': {
        target: 'http://localhost:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/email': {
        target: 'http://localhost:5003',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../dist-vue',
    emptyOutDir: true,
  }
})