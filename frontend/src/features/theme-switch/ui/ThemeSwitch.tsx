import { useLayoutEffect, useState } from 'react'
import { applyTheme, readTheme } from '../model/theme'

export default function ThemeSwitch({ remember }: { remember: boolean }) {
  const [theme, setTheme] = useState(() => readTheme(remember))
  useLayoutEffect(() => applyTheme(theme, remember), [theme, remember])

  return (
    <button
      type="button"
      className="text-button"
      aria-pressed={theme === 'dark'}
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
    >
      Тёмная тема
    </button>
  )
}
