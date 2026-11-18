import { useEffect } from 'react'
import { AboutPage } from '../pages/about'
import { DocumentsPage } from '../pages/documents'
import { HomePage } from '../pages/home'
import { NotFoundPage } from '../pages/not-found'
import { portalTitle } from '../shared/config/portal'
import { SiteHeader } from '../widgets/site-header'
import { SiteFooter } from '../widgets/site-footer'

const routes = new Map([
  ['/', { Page: HomePage, title: portalTitle }],
  ['/about', { Page: AboutPage, title: 'О нас' }],
  ['/documents', { Page: DocumentsPage, title: 'Документы портала' }],
])

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  const { Page, title } = routes.get(path) ?? {
    Page: NotFoundPage,
    title: 'Страница не найдена',
  }
  useEffect(() => {
    document.title = title === portalTitle ? title : `${title} — ${portalTitle}`
  }, [title])
  return (
    <div className="page">
      <SiteHeader path={path} />
      <main className="container main">
        <Page />
      </main>
      <SiteFooter />
    </div>
  )
}
