import { createMockBff } from './bff'

export function mockBrowserFetch(handle = createMockBff()) {
  let cookie = ''
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), window.location.origin)
    const headers = new Headers(init?.headers)
    if (cookie && init?.credentials === 'include') headers.set('Cookie', cookie)
    const response = await handle(new Request(url, { ...init, headers }))
    const session = response.headers.get('Set-Cookie')
    if (session) cookie = session.split(';')[0]
    return response
  }
}
