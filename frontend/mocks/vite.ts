import { Readable } from 'node:stream'
import type { Plugin } from 'vite'
import { createMockBff } from './bff.ts'

export function mockBff(): Plugin {
  const handle = createMockBff()
  return {
    name: 'mock-bff',
    configureServer(server) {
      server.middlewares.use('/api/v1', async (req, res, next) => {
        try {
          const origin = 'http://' + req.headers.host
          if (req.method === 'POST' && req.headers.origin !== origin) {
            res.writeHead(403).end()
            return
          }
          const headers = new Headers()
          for (const [name, value] of Object.entries(req.headers)) {
            if (value !== undefined)
              headers.set(name, Array.isArray(value) ? value.join(', ') : value)
          }
          const request = new Request(origin + req.originalUrl, {
            method: req.method,
            headers,
            ...(req.method === 'POST' && {
              body: Readable.toWeb(req),
              duplex: 'half',
            }),
          } as RequestInit)
          const response = await handle(request)
          res.writeHead(response.status, Object.fromEntries(response.headers))
          res.end(Buffer.from(await response.arrayBuffer()))
        } catch (error) {
          next(error)
        }
      })
    },
  }
}
