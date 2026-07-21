import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Stamped into the bundle AND written to dist/version.json so the running
// app can detect that a newer build has been deployed (Railway's static
// host sends no Cache-Control on the SPA shell, so phones can hold a stale
// shell for days — see src/freshShell.js).
const BUILD_ID = String(Date.now())

const writeVersionJson = () => ({
  name: 'write-version-json',
  apply: 'build',
  closeBundle() {
    const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist')
    if (fs.existsSync(dist)) {
      fs.writeFileSync(path.join(dist, 'version.json'), JSON.stringify({ buildId: BUILD_ID }))
    }
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), writeVersionJson()],
  base: '/',
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: true,
    exclude: ['node_modules', 'tests/**'],
  },
})
