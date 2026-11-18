import { readCookieConsent } from './cookieConsent'

export type Theme = 'light' | 'dark'

const storageKey = 'portal-theme'

export function readTheme(): Theme {
  try {
    if (
      readCookieConsent()?.functional &&
      localStorage.getItem(storageKey) === 'dark'
    ) {
      return 'dark'
    }
  } catch {
    // Browser storage can be disabled.
  }
  return 'light'
}

export function applyTheme(theme: Theme, remember: boolean) {
  document.documentElement.dataset.theme = theme
  try {
    if (remember) localStorage.setItem(storageKey, theme)
    else localStorage.removeItem(storageKey)
  } catch {
    // The selected theme still applies to the current page.
  }
}
