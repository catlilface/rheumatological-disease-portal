import './header.css'
import { portalTitle } from '../../../shared/config/portal'

export default function SiteHeader({ path }: { path: string }) {
  return (
    <header className="header">
      <div className="container header__inner">
        <a className="brand" href="/">
          {portalTitle}
        </a>
        <nav className="header__nav" aria-label="Основная навигация">
          <a
            href="/documents"
            aria-current={path === '/documents' ? 'page' : undefined}
          >
            Документы
          </a>
          <a
            href="/about"
            aria-current={path === '/about' ? 'page' : undefined}
          >
            О нас
          </a>
        </nav>
      </div>
    </header>
  )
}
