import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// En desarrollo, Vite reenvía /api al backend FastAPI del PC.
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify('0.6 · Fase 4 (entregas y notas)') },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Florida Teacher App',
        short_name: 'Florida Profe',
        description: 'Gestión de Florida Oberta desde la tablet',
        lang: 'es',
        start_url: '/',
        display: 'standalone',
        orientation: 'any',
        background_color: '#f6f7f9',
        theme_color: '#c8102e',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // La versión nueva sustituye a la antigua en cuanto se detecta (sin quedarse en caché)
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        // Las llamadas a la API nunca se cachean: siempre van al PC.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [{ urlPattern: /\/api\//, handler: 'NetworkOnly' }],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    proxy: { '/api': { target: API_TARGET, changeOrigin: true } },
  },
})
