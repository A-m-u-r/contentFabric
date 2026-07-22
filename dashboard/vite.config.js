import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: [
      'openshorts.app',
      'www.openshorts.app'
    ],
    // On Windows + Docker the bind-mount doesn't forward inotify events, so
    // Vite's HMR never sees host edits. Polling makes the container re-check
    // files on a timer instead — edits show up without restarting the container.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/videos': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/thumbnails': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/gallery': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/video': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/render': {
        target: 'http://renderer:3100',
        changeOrigin: true,
      }
    }
  }
})
