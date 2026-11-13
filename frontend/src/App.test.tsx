import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App placeholder', () => {
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

  it('shows the medical disclaimer in the footer', () => {
    render(<App />)

    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'не заменяет консультацию врача',
    )
  })
})
