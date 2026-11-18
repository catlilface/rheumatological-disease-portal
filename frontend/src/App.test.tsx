import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App'

afterEach(() => {
  window.history.replaceState(null, '', '/')
  localStorage.clear()
})

describe('App', () => {
  it('shows the coming soon message', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Ревматологический портал',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Скоро здесь появится система/)).toBeInTheDocument()
  })

  it.each(['/', '/documents', '/about'])(
    'shows the medical disclaimer at %s',
    (path) => {
      window.history.replaceState(null, '', path)
      render(<App />)

      const footer = within(screen.getByRole('contentinfo'))
      expect(
        footer.getByText(/не является диагнозом или клинической рекомендацией/),
      ).toBeInTheDocument()
      expect(
        footer.getByRole('link', { name: /полный текст дисклеймера/i }),
      ).toHaveAttribute('href', '/policy/medical-advices')
    },
  )

  it('lists all seven PDF policies and the operator page', () => {
    window.history.replaceState(null, '', '/documents')
    render(<App />)

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

  it.each([
    ['Принять необязательные', true],
    ['Отклонить необязательные', false],
  ])('persists the choice made with "%s"', (action, value) => {
    const notice = () =>
      screen.queryByRole('region', { name: 'Использование cookie' })
    const { unmount } = render(<App />)

    expect(notice()).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: action }))
    expect(notice()).not.toBeInTheDocument()
    expect(localStorage.getItem('cookie-consent')).toBe(
      JSON.stringify({ functional: value, analytics: value }),
    )

    unmount()
    render(<App />)
    expect(notice()).not.toBeInTheDocument()
  })

  it('lets the user revise consent from the footer', () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ functional: true, analytics: true }),
    )
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Настройки cookie' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /аналитические/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }))

    expect(localStorage.getItem('cookie-consent')).toBe(
      JSON.stringify({ functional: true, analytics: false }),
    )
  })
})

it('switches theme, remembers it with functional consent and clears it on withdrawal', () => {
  const { unmount } = render(<App />)
  const toggle = screen.getByRole('button', { name: 'Тёмная тема' })
  expect(document.documentElement.dataset.theme).toBe('light')
  fireEvent.click(toggle)
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem('portal-theme')).toBeNull()
  fireEvent.click(
    screen.getByRole('button', { name: 'Принять необязательные' }),
  )
  unmount()
  render(<App />)
  expect(screen.getByRole('button', { name: 'Тёмная тема' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  fireEvent.click(screen.getByRole('button', { name: 'Настройки cookie' }))
  fireEvent.click(
    screen.getByRole('button', { name: 'Отклонить необязательные' }),
  )
  expect(localStorage.getItem('portal-theme')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }))
  expect(document.documentElement.dataset.theme).toBe('light')
})
