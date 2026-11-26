import { useEffect, type ReactNode } from 'react'
import { Route, Routes } from 'react-router'

import {
  AboutPage,
  CabinetPage,
  ArticlePage,
  DoctorPage,
  DocumentsPage,
  HomePage,
  LibraryPage,
  NotFoundPage,
  ResultPage,
  ScreeningPage,
  ScreeningSessionPage,
} from '@pages'
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
            path="cabinet"
            caseSensitive
            element={
              <PageContent title="nav.cabinet">
                <CabinetPage />
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
            path="screening"
            caseSensitive
            element={
              <PageContent title="nav.screening">
                <ScreeningPage />
              </PageContent>
            }
          />
          <Route
            path="screening/:screeningId"
            caseSensitive
            element={
              <PageContent title="nav.screening">
                <ScreeningSessionPage />
              </PageContent>
            }
          />
          <Route
            path="results/:resultId/versions/:version"
            caseSensitive
            element={
              <PageContent title="result.title">
                <ResultPage />
              </PageContent>
            }
          />
          <Route
            path="library"
            caseSensitive
            element={
              <PageContent title="nav.library">
                <LibraryPage />
              </PageContent>
            }
          />
          <Route
            path="library/:slug"
            caseSensitive
            element={
              <PageContent title="nav.library">
                <ArticlePage />
              </PageContent>
            }
          />
          <Route
            path="doctor"
            caseSensitive
            element={
              <PageContent title="nav.doctor">
                <DoctorPage />
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
