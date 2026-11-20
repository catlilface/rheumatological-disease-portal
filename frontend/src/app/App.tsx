import { useEffect, type ReactNode } from 'react'
import { Route, Routes } from 'react-router'

import { AboutPage, DocumentsPage, HomePage, NotFoundPage } from '@pages'
import { SiteFooter, SiteHeader } from '@widgets'
import { t, type MessageKey } from '@shared/i18n'

function PageContent({
  title,
  children,
}: {
  title?: MessageKey
  children: ReactNode
}) {
  useEffect(() => {
    const portal = t('portal.title')
    document.title = title
      ? t('portal.pageTitle', { page: t(title), portal })
      : portal
  }, [title])

  return children
}

export default function App() {
  return (
    <div className="page">
      <SiteHeader />
      <main className="container main">
        <Routes>
          <Route
            index
            element={
              <PageContent>
                <HomePage />
              </PageContent>
            }
          />
          <Route
            path="about"
            caseSensitive
            element={
              <PageContent title="nav.about">
                <AboutPage />
              </PageContent>
            }
          />
          <Route
            path="documents"
            caseSensitive
            element={
              <PageContent title="documents.title">
                <DocumentsPage />
              </PageContent>
            }
          />
          <Route
            path="*"
            element={
              <PageContent title="notFound.title">
                <NotFoundPage />
              </PageContent>
            }
          />
        </Routes>
      </main>
      <SiteFooter />
    </div>
  )
}
