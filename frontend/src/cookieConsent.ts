const storageKey = 'cookie-consent'
export const optionalCookies = [
  {
    id: 'functional',
    label: 'Функциональные',
    description: 'Дополнительные настройки интерфейса.',
  },
  {
    id: 'analytics',
    label: 'Аналитические',
    description: 'Статистика использования сайта.',
  },
] as const

export type CookieConsent = Record<
  (typeof optionalCookies)[number]['id'],
  boolean
>

export const allAccepted: CookieConsent = { functional: true, analytics: true }
export const allRejected: CookieConsent = {
  functional: false,
  analytics: false,
}

export function readCookieConsent(): CookieConsent | null {
  try {
    const saved = localStorage.getItem(storageKey)
    if (!saved) return null

    const consent = JSON.parse(saved)
    if (
      typeof consent?.functional === 'boolean' &&
      typeof consent?.analytics === 'boolean'
    ) {
      return { functional: consent.functional, analytics: consent.analytics }
    }
  } catch {
    // Missing or unreadable consent requires a new choice.
  }

  return null
}

export function saveCookieConsent(consent: CookieConsent) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(consent))
  } catch {
    // The choice still applies for the current page when storage is unavailable.
  }
}
