import './home.css'
import { Link } from 'react-router'
import { t } from '@shared/i18n'

export default function HomePage() {
  return (
    <section className="hero">
      <p className="hero__status">{t('home.status')}</p>
      <h1>{t('portal.title')}</h1>
      <p className="hero__intro">{t('home.intro')}</p>
      <Link className="primary-link" to="/documents">
        {t('documents.title')}
      </Link>
    </section>
  )
}
