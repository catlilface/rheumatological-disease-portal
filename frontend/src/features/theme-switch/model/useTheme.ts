import { useLayoutEffect, useState } from 'react'
import { readTheme, syncThemePreference, type Theme } from './theme'

export function useTheme(remember: boolean) {
  const [{ theme, canChange }, setSelection] = useState(() =>
    readTheme(remember),
  )

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  function changeTheme(nextTheme: Theme) {
    if (!canChange) return
    if (remember && !syncThemePreference(nextTheme, true)) {
      setSelection({ theme, canChange: false })
      return
    }

    setSelection({ theme: nextTheme, canChange: true })
  }

  function syncConsent(nextRemember: boolean) {
    if (nextRemember && !canChange) return
    if (!syncThemePreference(theme, nextRemember)) {
      setSelection({ theme, canChange: false })
    }
  }

  return { theme, canChange, changeTheme, syncConsent }
}
