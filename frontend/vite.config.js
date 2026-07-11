import { defineConfig } from 'vite';

export default defineConfig(({ command }) => ({
  // In production builds the base is injected by the deploy workflow
  // via --base flag so it matches the GitHub Pages sub-path.
  server: {
    host: true,
    proxy: {
      // WebSocket calls go to the local FastAPI server during dev. The backend
      // self-signs a TLS cert for local runs (see backend/api.py) so the cart
      // bookmarklet can reach it over wss:// from tcgplayer.com; `secure: false`
      // tells this server-side proxy to accept that self-signed cert.
      '/ws': {
        target: 'https://localhost:8000',
        ws: true,
        rewriteWsOrigin: true,
        secure: false,
      },
      // Art assets (Pokémon ASCII, app logo) are served by FastAPI.
      '/art': {
        target: 'https://localhost:8000',
        secure: false,
      },
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
}));
