import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { t } from './src/shared/i18n/index.ts'

const bff = new URL(process.env.BFF_PROXY_TARGET ?? 'https://mis.clfs.wtf')

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
  server: {
    proxy: {
      '/api/': {
        target: bff.origin,
        changeOrigin: true,
        ws: true,
        configure(proxy) {
          proxy.on('proxyReq', (upstream, request) => {
            // The upstream sees its own origin only for same-origin browser requests.
            const https =
              'encrypted' in request.socket && request.socket.encrypted
            const origin = `${https ? 'https' : 'http'}://${request.headers.host}`
            if (request.headers.origin === origin) {
              upstream.setHeader('Origin', bff.origin)
            } else {
              upstream.removeHeader('Origin')
            }
          })
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/app/testing/setup.ts'],
  },
})
