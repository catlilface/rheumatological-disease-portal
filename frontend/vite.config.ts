import react from '@vitejs/plugin-react'
import type { Plugin, ViteDevServer } from 'vite'
import { defineConfig } from 'vitest/config'
import { policyLinks } from './src/policies.js'

function policyDocuments(): Plugin {
  const pdfs = new Map(policyLinks.map(({ href }) => [href, `${href}.pdf`]))

  function servePolicyDocuments(server: Pick<ViteDevServer, 'middlewares'>) {
    server.middlewares.use((request, _response, next) => {
      if (request.url) {
        const [path, query] = request.url.split(/\?(.*)/s)
        const pdf = pdfs.get(path.replace(/\/+$/, ''))
        if (pdf) request.url = query ? `${pdf}?${query}` : pdf
      }

      next()
    })
  }

  return {
    name: 'policy-documents',
    configureServer: servePolicyDocuments,
    configurePreviewServer: servePolicyDocuments,
  }
}

export default defineConfig({
  plugins: [react(), policyDocuments()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
