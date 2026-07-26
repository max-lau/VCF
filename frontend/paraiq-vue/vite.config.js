import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Let the SPA handle page-load requests (e.g. hard refresh on /intake)
// while still proxying XHR/fetch API calls to the backend.
function spaBypass(req) {
  const url = req.url || ''
  // Never bypass actual file downloads — proxy them to the backend
  if (url.startsWith('/intake/file/')) {
    return null
  }
  // Vite dev-server assets must be served by Vite, not proxied to the backend
  if (url.startsWith('/assets/')) {
    return url
  }
  const accept = req.headers?.accept || ''
  if (accept.includes('text/html')) {
    return '/index.html'
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
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/auth': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true
      },
      '/api': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      },
      '/cases': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true
      },
      '/intake': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/dashboard': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/communications': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/email': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      },
      // Catch-all for any other SPA route (document-inbox, vcf-account-prep,
      // batch-intake, esign, etc.). HTML navigation requests get index.html;
      // everything else falls through to the dev server.
      '^/.*': {
        target: 'http://127.0.0.1:5003',
        changeOrigin: true,
        bypass: spaBypass
      }
    }
  },
  build: {
    outDir: '../dist-vue',
    emptyOutDir: true,
  }
})