import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { createMockBff } from '../../mocks/bff'
import { article, doctorRoute, survey } from '../../mocks/fixtures'
import { t } from '@shared/i18n'
import App from './App'
import { mockBrowserFetch } from '../../mocks/browser-fetch'

afterEach(() => vi.unstubAllGlobals())

function renderApp(path = '/', pendingPolls = 0) {
  vi.stubGlobal('fetch', mockBrowserFetch(createMockBff({ pendingPolls })))
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

const button = (name: string) => screen.getByRole('button', { name })
const clickNav = (name: string) =>
  fireEvent.click(
    within(
      screen.getByRole('navigation', { name: t('nav.primary') }),
    ).getByRole('link', { name }),
  )

it('navigates to the public library, article and doctor guide through BFF mocks', async () => {
  renderApp()
  clickNav(t('nav.library'))
  fireEvent.click(await screen.findByRole('link', { name: article.title }))
  expect(
    await screen.findByRole('heading', { name: article.title }),
  ).toBeInTheDocument()
  expect(screen.getByText(article.body_markdown)).toBeInTheDocument()
  clickNav(t('nav.doctor'))
  expect(
    await screen.findByRole('heading', { name: doctorRoute.title }),
  ).toBeInTheDocument()
})

it('requires confirmation, displays pending and opens the exact result version', async () => {
  renderApp('/screening', 1)
  const confirm = await screen.findByRole('checkbox', {
    name: survey.confirmation_text,
  })
  expect(button(t('screening.start'))).toBeDisabled()
  fireEvent.click(confirm)
  fireEvent.click(button(t('screening.start')))
  expect(await screen.findByText(t('api.pending'))).toBeInTheDocument()

  const pick = async (question: string, choice: string) => {
    const field = await screen.findByRole(
      'group',
      { name: question },
      { timeout: 2500 },
    )
    fireEvent.click(within(field).getByRole('radio', { name: choice }))
    await screen.findByText(t('screening.saved'), {}, { timeout: 2500 })
  }
  await pick('Тестовый признак? *', t('screening.no'))
  await pick('Тестовый вариант *', 'Первый')
  await pick('Тестовый красный флаг? *', t('screening.yes'))
  expect(screen.getByRole('alert')).toHaveTextContent(survey.urgent_notice)
  const earlyResult = screen.getByRole('link', {
    name: t('screening.viewResult'),
  })
  expect(earlyResult).toHaveAttribute(
    'href',
    expect.stringMatching(/\/versions\/1$/),
  )
  fireEvent.click(button(t('screening.continue')))
  await screen.findByText(t('screening.saved'), {}, { timeout: 2500 })
  fireEvent.click(button(t('screening.complete')))
  expect(
    await screen.findByRole(
      'heading',
      { name: t('result.title') },
      { timeout: 2500 },
    ),
  ).toBeInTheDocument()
  expect(
    await screen.findByText(t('result.version', { version: '2' })),
  ).toBeInTheDocument()
  expect(screen.getByText(t('result.redFlag'))).toBeInTheDocument()
}, 10_000)

it('renders a denied private result without creating a session or showing result details', async () => {
  renderApp('/results/02995529-91a3-4550-aa71-aa9fe798d274/versions/1')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    t('api.sessionRequired'),
  )
  expect(screen.queryByText(t('result.low'))).not.toBeInTheDocument()
})
