import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { t } from '@shared/i18n'
import App from './App'

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('App', () => {
  it.each(['/', '/documents', '/about', '/missing'])(
    'shows the medical disclaimer at %s',
    (path) => {
      renderApp(path)

      const footer = within(screen.getByRole('contentinfo'))
      expect(footer.getByText(t('disclaimer.summary'))).toBeInTheDocument()
      expect(
        footer.getByRole('link', { name: t('disclaimer.fullText') }),
      ).toHaveAttribute('href', '/policy/medical-advices')
    },
  )

  it('lists all seven PDF policies and the operator page', () => {
    renderApp('/documents')

    const main = within(screen.getByRole('main'))
    expect(
      main.getAllByRole('link').map((link) => link.getAttribute('href')),
    ).toEqual([
      '/policy/personal-info',
      '/policy/personal-info-agreement',
      '/policy/user-agreement',
      '/policy/medical-advices',
      '/policy/ai',
      '/policy/account-deletion',
      '/policy/cookies',
      '/about',
    ])
  })

  it('updates the page title and marks the current navigation link', () => {
    renderApp()
    const link = screen.getByRole('link', { name: t('nav.documents') })
    fireEvent.click(link)

    expect(link).toHaveAttribute('aria-current', 'page')
    expect(document.title).toBe(
      t('portal.pageTitle', {
        page: t('documents.title'),
        portal: t('portal.title'),
      }),
    )
  })
})

describe('Cookie consent', () => {
  it.each([
    ['cookies.accept', true],
    ['cookies.reject', false],
  ] as const)('persists the choice made with "%s"', (action, value) => {
    const notice = () =>
      screen.queryByRole('region', { name: t('cookies.title') })
    const { unmount } = renderApp()

    expect(notice()).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: t(action) }))
    expect(localStorage.getItem('cookie-consent')).toBe(
      JSON.stringify({ functional: value, analytics: value }),
    )
    expect(notice()).not.toBeInTheDocument()

    unmount()
    renderApp()
    expect(notice()).not.toBeInTheDocument()
  })

  it('lets the user revise consent from the footer and restores focus after saving', () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ functional: true, analytics: true }),
    )
    renderApp()

    const settings = screen.getByRole('button', { name: t('cookies.settings') })
    fireEvent.click(settings)
    const group = screen.getByRole('group', { name: t('cookies.optional') })
    expect(group).toHaveFocus()
    const analytics = within(group).getByRole('checkbox', {
      name: t('cookies.analytics.label'),
    })
    expect(analytics).toHaveAccessibleDescription(
      t('cookies.analytics.description'),
    )
    expect(analytics).toBeChecked()
    fireEvent.click(analytics)
    fireEvent.click(
      within(group).getByRole('button', { name: t('cookies.save') }),
    )

    expect(localStorage.getItem('cookie-consent')).toBe(
      JSON.stringify({ functional: true, analytics: false }),
    )
    expect(settings).toHaveFocus()
  })
})

describe('Theme', () => {
  const themeControl = () =>
    screen.getByRole('combobox', { name: t('theme.label') })

  it('switches among three themes and persists the selection with functional consent', () => {
    const { unmount } = renderApp()
    expect(themeControl()).toHaveValue('auto')
    expect(document.documentElement.dataset.theme).toBe('auto')

    fireEvent.change(themeControl(), { target: { value: 'dark' } })
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('portal-theme')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: t('cookies.accept') }))
    expect(localStorage.getItem('portal-theme')).toBe('dark')

    unmount()
    renderApp()
    expect(themeControl()).toHaveValue('dark')
    fireEvent.change(themeControl(), { target: { value: 'light' } })
    expect(localStorage.getItem('portal-theme')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    fireEvent.change(themeControl(), { target: { value: 'auto' } })
    expect(localStorage.getItem('portal-theme')).toBe('auto')
    expect(document.documentElement.dataset.theme).toBe('auto')

    fireEvent.click(screen.getByRole('button', { name: t('cookies.settings') }))
    fireEvent.click(screen.getByRole('button', { name: t('cookies.reject') }))
    expect(localStorage.getItem('portal-theme')).toBeNull()
  })

  it('disables the theme selector if storage cannot be read', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    renderApp()

    expect(warn).toHaveBeenCalled()
    expect(themeControl()).toBeDisabled()
    expect(themeControl()).toHaveAccessibleDescription(t('theme.unavailable'))
    expect(document.documentElement.dataset.theme).toBe('auto')
  })

  it('preserves the previously applied theme if writing the new choice fails', () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ functional: true, analytics: false }),
    )
    localStorage.setItem('portal-theme', 'light')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    renderApp()

    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('Storage unavailable')
      })
    fireEvent.change(themeControl(), { target: { value: 'dark' } })

    expect(warn).toHaveBeenCalled()
    expect(themeControl()).toBeDisabled()
    expect(themeControl()).toHaveValue('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('portal-theme')).toBe('light')

    setItem.mockRestore()
    fireEvent.click(screen.getByRole('button', { name: t('cookies.settings') }))
    fireEvent.click(screen.getByRole('button', { name: t('cookies.reject') }))
    expect(localStorage.getItem('portal-theme')).toBeNull()
    expect(themeControl()).toBeDisabled()
  })
})
