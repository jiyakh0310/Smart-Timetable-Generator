import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the browser talks to Vite (5173); /api calls are forwarded to Flask (5000).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
    testTimeout: 20000, // long multi-step UI flows in jsdom can exceed the 5s default on a busy machine
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true } },
  },
});
