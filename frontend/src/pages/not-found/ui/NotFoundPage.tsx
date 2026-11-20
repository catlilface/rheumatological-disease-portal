import { Link } from 'react-router'
import { t } from '@shared/i18n'

export default function NotFoundPage() {
  return (
    <article className="article">
      <h1>{t('notFound.title')}</h1>
      <Link to="/">{t('notFound.homeLink')}</Link>
    </article>
  )
}
