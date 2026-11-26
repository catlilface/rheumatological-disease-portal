import './header.css'
import { Link, NavLink } from 'react-router'
import { t } from '@shared/i18n'

export default function SiteHeader() {
  return (
    <header className="header">
      <div className="container header__inner">
        <Link className="brand" to="/">
          <img src="/favicon.svg" width={32} height={32} alt="" />
          {t('portal.title')}
        </Link>
        <nav className="header__nav" aria-label={t('nav.primary')}>
          <NavLink to="/screening" caseSensitive>
            {t('nav.screening')}
          </NavLink>
          <NavLink to="/library" caseSensitive>
            {t('nav.library')}
          </NavLink>
          <NavLink to="/doctor" end caseSensitive>
            {t('nav.doctor')}
          </NavLink>
          <NavLink to="/cabinet" end caseSensitive>
            {t('nav.cabinet')}
          </NavLink>
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
