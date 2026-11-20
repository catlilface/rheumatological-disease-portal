export const themes = ['auto', 'light', 'dark'] as const

export type Theme = (typeof themes)[number]

const storageKey = 'portal-theme'
const defaultTheme = 'auto'

function isTheme(value: string | null): value is Theme {
  return themes.some((theme) => theme === value)
}

export function readTheme(remember: boolean): {
  theme: Theme
  canChange: boolean
} {
  try {
    const saved = localStorage.getItem(storageKey)
    if (!remember) localStorage.removeItem(storageKey)
    return {
      theme: remember && isTheme(saved) ? saved : defaultTheme,
      canChange: true,
    }
  } catch (error) {
    console.warn('Could not initialize the portal theme preference', error)
    return { theme: defaultTheme, canChange: false }
  }
}

export function syncThemePreference(theme: Theme, remember: boolean): boolean {
  try {
    if (remember) localStorage.setItem(storageKey, theme)
    else localStorage.removeItem(storageKey)
    return true
  } catch (error) {
    console.warn('Could not update the portal theme preference', error)
    return false
  }
}
