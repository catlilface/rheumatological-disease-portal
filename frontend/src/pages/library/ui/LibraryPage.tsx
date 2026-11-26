import { useCallback } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { bff } from '@shared/api/client'
import { useBffQuery } from '@shared/api/useBff'
import { t } from '@shared/i18n'
import { RequestStatus } from '@shared/ui/RequestStatus'
import { ReviewedMaterial } from '@shared/ui/ReviewedMaterial'

export function LibraryPage() {
  const [params] = useSearchParams()
  const page = Number(params.get('offset'))
  const offset = Number.isSafeInteger(page) && page >= 0 ? page : 0
  return (
    <section className="article portal-flow">
      <h1>{t('nav.library')}</h1>
      <LibraryList key={offset} offset={offset} />
    </section>
  )
}

function LibraryList({ offset }: { offset: number }) {
  const load = useCallback(
    (signal: AbortSignal) => bff.articles(offset, signal),
    [offset],
  )
  const { state, reload } = useBffQuery(load)
  if (state.status !== 'success')
    return <RequestStatus {...state} onRetry={reload} />
  const { items, total, limit } = state.data
  return (
    <>
      {items.length === 0 ? (
        <p>{t('library.empty')}</p>
      ) : (
        <ul className="material-list">
          {items.map((article) => (
            <li key={article.slug}>
              <h2>
                <Link to={'/library/' + encodeURIComponent(article.slug)}>
                  {article.title}
                </Link>
              </h2>
              <p>{article.summary}</p>
            </li>
          ))}
        </ul>
      )}
      {(offset > 0 || offset + limit < total) && (
        <nav className="portal-actions" aria-label={t('library.pagination')}>
          {offset > 0 && (
            <Link to={'?offset=' + Math.max(0, offset - limit)}>
              {t('library.previous')}
            </Link>
          )}
          {offset + limit < total && (
            <Link to={'?offset=' + (offset + limit)}>{t('library.next')}</Link>
          )}
        </nav>
      )}
    </>
  )
}

export function ArticlePage() {
  const { slug = '' } = useParams()
  return <ArticleContent key={slug} slug={slug} />
}

function ArticleContent({ slug }: { slug: string }) {
  const load = useCallback(
    (signal: AbortSignal) => bff.article(slug, signal),
    [slug],
  )
  const { state, reload } = useBffQuery(load)
  return (
    <article className="article portal-flow">
      <Link to="/library">{t('nav.library')}</Link>
      {state.status === 'success' ? (
        <ReviewedMaterial material={state.data} />
      ) : (
        <RequestStatus {...state} onRetry={reload} />
      )}
    </article>
  )
}
