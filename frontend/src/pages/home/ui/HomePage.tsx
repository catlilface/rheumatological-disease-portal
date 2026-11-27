import './home.css'
import { Link } from 'react-router'
import { t } from '@shared/i18n'

const sections = [
  { id: 'screening', path: '/screening' },
  { id: 'library', path: '/library' },
  { id: 'doctor', path: '/doctor' },
] as const

function HomeSections() {
  return (
    <section className="home-sections" aria-labelledby="home-sections">
      <h2 id="home-sections">{t('home.sections')}</h2>
      <ul>
        {sections.map(({ id, path }) => (
          <li key={id}>
            <Link
              className="home-section"
              to={path}
              aria-labelledby={`home-${id}-label`}
              aria-describedby={`home-${id}-description`}
            >
              <span
                className={`home-section__symbol home-section__symbol--${id}`}
                aria-hidden="true"
              />
              <div>
                <h3 id={`home-${id}-label`}>{t(`nav.${id}`)}</h3>
                <p id={`home-${id}-description`}>{t(`home.${id}`)}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function HomePage() {
  return (
    <div className="home">
      <section className="hero" aria-labelledby="home-title">
        <div className="hero__content">
          <h1 id="home-title">{t('home.title')}</h1>
          <p className="hero__intro">{t('home.intro')}</p>
          <div className="hero__actions">
            <Link className="primary-link" to="/screening">
              {t('home.start')}
            </Link>
            <Link className="secondary-link" to="/library">
              {t('home.read')}
            </Link>
          </div>
        </div>
        <div className="hero__visual" aria-hidden="true">
          <img src="/images/joint-hero.webp" alt="" fetchPriority="high" />
        </div>
      </section>
      <HomeSections />
    </div>
  )
}
