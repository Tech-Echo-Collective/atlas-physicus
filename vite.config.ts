import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // MapLibre is a self-contained WebGL renderer; keep its dedicated vendor
    // chunk cacheable without treating the known engine size as app growth.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks: {
          geography: ['topojson-client', 'world-atlas/countries-110m.json'],
          maplibre: ['maplibre-gl'],
          react: ['react', 'react-dom'],
        },
      },
    },
  },
});
