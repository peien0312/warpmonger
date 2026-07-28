import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Builds straight into the Flask app's static tree; /game serves the
// built index.html (beta-gated), assets load from /static/game/.
export default defineConfig({
  base: '/static/game/',
  build: {
    outDir: '../static/game',
    emptyOutDir: true,
  },
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5006',
        changeOrigin: true,
      },
    },
  },
})
