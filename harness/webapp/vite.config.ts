import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The backend (harness/backend, FastAPI) has no CORS middleware, so in dev we
// proxy the API through Vite instead of crossing origins in the browser.
//
//   VITE_BACKEND_PROXY_TARGET  -> where the running backend listens (default :8766)
//   VITE_API_BASE              -> absolute base the BUILT app calls (optional;
//                                 defaults to the relative "/api" path, which a
//                                 reverse proxy / the backend's static router must
//                                 forward in production).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8766'
  return {
    plugins: [react()],
    // The published closed-beta site serves the browser build under /app/,
    // so production asset URLs must be prefixed. Dev stays at the root.
    base: mode === 'production' ? '/app/' : '/',
    server: {
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
