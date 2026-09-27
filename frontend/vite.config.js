import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backend = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind the IPv4 loopback explicitly. Vite's default "localhost" can resolve to
    // ::1, which leaves http://127.0.0.1:5173 unreachable and out of step with the
    // backend (uvicorn listens on 127.0.0.1) and with CORS_ORIGINS.
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
