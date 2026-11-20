import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { t } from './src/shared/i18n/index.ts'

export default defineConfig({
  plugins: [
    react(),
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
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/app/testing/setup.ts'],
  },
})
