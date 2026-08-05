import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: [
      'openshorts.app',
      'www.openshorts.app'
    ],
    // Docker maps container:5173 -> host:5175, so the browser's HMR client
    // must be told the external port explicitly — otherwise it can't build
    // a valid ws:// URL (ws://localhost:undefined) and HMR silently dies.
    // VITE_HMR_CLIENT_PORT is only set in docker-compose.yml; plain
    // `npm run dev` on the host leaves it unset and Vite auto-detects.
    hmr: {
      clientPort: process.env.VITE_HMR_CLIENT_PORT
        ? Number(process.env.VITE_HMR_CLIENT_PORT)
        : undefined,
    },
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
