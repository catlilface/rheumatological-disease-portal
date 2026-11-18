import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { applyTheme, readTheme } from './theme'
import AboutPage from './AboutPage'
import { CookieNotice } from './CookieNotice'
import { readCookieConsent, saveCookieConsent } from './cookieConsent'
import { policyLinks } from './policies'

const portalTitle = 'Ревматологический портал'

function HomePage() {
  return (
    <section className="hero">
      <p className="hero__status">Сайт находится в разработке</p>
      <h1>{portalTitle}</h1>
      <p className="hero__intro">
        Скоро здесь появится система, которая поможет вовремя заметить признаки
        ревматологических заболеваний и подскажет, к какому врачу обратиться.
      </p>
      <a className="primary-link" href="/documents">
        Документы портала
      </a>
    </section>
  )
}

function DocumentsPage() {
  return (
    <article className="article">
      <h1>Документы портала</h1>
      <ul className="document-list">
        {policyLinks.map(({ title, description, href }) => (
          <li key={href}>
            <div>
              <a href={href}>{title}</a>
              <p>{description}</p>
            </div>
            <span>PDF</span>
          </li>
        ))}
        <li>
          <div>
            <a href="/about">Сведения об операторе</a>
            <p>
              Реквизиты владельца сайта и сведения об организации обработки
              персональных данных.
            </p>
          </div>
        </li>
      </ul>
    </article>
  )
}

function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  const [consent, setConsent] = useState(readCookieConsent)
  const [theme, setTheme] = useState(readTheme)
  const rememberTheme = consent?.functional === true
  useLayoutEffect(
    () => applyTheme(theme, rememberTheme),
    [theme, rememberTheme],
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const cookieSettingsButton = useRef<HTMLButtonElement>(null)
  const title =
    path === '/about'
      ? 'О нас'
      : path === '/documents'
        ? 'Документы портала'
        : portalTitle

  useEffect(() => {
    document.title =
      title === portalTitle ? portalTitle : `${title} — ${portalTitle}`
  }, [title])

  return (
    <div className="page">
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

      <main className="container main">
        {path === '/' && <HomePage />}
        {path === '/about' && <AboutPage />}
        {path === '/documents' && <DocumentsPage />}
        {!['/', '/about', '/documents'].includes(path) && (
          <article className="article">
            <h1>Страница не найдена</h1>
            <a href="/">На главную</a>
          </article>
        )}
      </main>

      <footer className="footer">
        <div className="container footer__inner">
          <div>
            <h2>Медицинский дисклеймер</h2>
            <p>
              Информация на сайте носит справочный характер, не является
              диагнозом или клинической рекомендацией и не заменяет консультацию
              врача.
            </p>
            <a href="/policy/medical-advices">Полный текст дисклеймера (PDF)</a>
          </div>
          <nav className="footer__nav" aria-label="Информация о портале">
            <a href="/documents">Документы портала</a>
            <a href="/about">Сведения об операторе</a>
            <button
              type="button"
              className="text-button"
              aria-pressed={theme === 'dark'}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              Тёмная тема
            </button>
            <button
              type="button"
              className="text-button"
              ref={cookieSettingsButton}
              onClick={() => setSettingsOpen(true)}
            >
              Настройки cookie
            </button>
          </nav>
        </div>
      </footer>

      {(!consent || settingsOpen) && (
        <CookieNotice
          consent={consent}
          settingsOpen={settingsOpen}
          onOpenSettings={() => setSettingsOpen(true)}
          onSave={(choice) => {
            saveCookieConsent(choice)
            setConsent(choice)
            setSettingsOpen(false)
            cookieSettingsButton.current?.focus()
          }}
        />
      )}
    </div>
  )
}

export default App
