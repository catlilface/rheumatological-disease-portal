import './header.css'
import { Link, NavLink } from 'react-router'
import { t } from '@shared/i18n'

export default function SiteHeader() {
  return (
    <header className="header">
      <div className="container header__inner">
        <Link className="brand" to="/">
          {t('portal.title')}
        </Link>
        <nav className="header__nav" aria-label={t('nav.primary')}>
          <NavLink to="/documents" end caseSensitive>
            {t('nav.documents')}
          </NavLink>
          <NavLink to="/about" end caseSensitive>
            {t('nav.about')}
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
