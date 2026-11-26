import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { t } from './src/shared/i18n/index.ts'
import { mockBff } from './mocks/vite.ts'

export default defineConfig(({ command, mode }) => ({
  plugins: [
    react(),
    ...(command === 'serve' && mode === 'mock' ? [mockBff()] : []),
    {
      name: 'portal-metadata',
      transformIndexHtml() {
        return [
          { tag: 'title', children: t('portal.title'), injectTo: 'head' },
          {
            tag: 'meta',
            attrs: { name: 'description', content: t('portal.description') },
            injectTo: 'head',
          },
        ]
      },
    },
  ],
  resolve: { tsconfigPaths: true },
  server: {
    proxy:
      mode === 'mock'
        ? undefined
        : {
            '/api/': {
              target: process.env.BFF_PROXY_TARGET ?? 'http://localhost:8000',
              ws: true,
            },
          },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/app/testing/setup.ts'],
  },
}))
