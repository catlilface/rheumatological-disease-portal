import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { expect, it } from 'vitest'
import { t } from '@shared/i18n'
import App from './App'

function CurrentPath() {
  const { pathname } = useLocation()
  return <output aria-label="Текущий маршрут">{pathname}</output>
}

it.each([
  ['nav.screening', '/screening'],
  ['nav.library', '/library'],
  ['nav.doctor', '/doctor'],
] as const)('opens the MVP page %s from the main navigation', (label, path) => {
  render(
    <MemoryRouter>
      <App />
      <CurrentPath />
    </MemoryRouter>,
  )
  const link = within(
    screen.getByRole('navigation', { name: t('nav.primary') }),
  ).getByRole('link', { name: t(label) })
  fireEvent.click(link)
  expect(screen.getByLabelText('Текущий маршрут')).toHaveTextContent(path)
  expect(link).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('heading', { name: t(label) })).toBeInTheDocument()
})

it('opens the versioned result directly', () => {
  render(
    <MemoryRouter
      initialEntries={[
        '/results/02995529-91a3-4550-aa71-aa9fe798d274/versions/2',
      ]}
    >
      <App />
    </MemoryRouter>,
  )
  expect(
    screen.getByRole('heading', { name: t('result.title') }),
  ).toBeInTheDocument()
})
