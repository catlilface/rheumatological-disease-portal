const storageKey = 'cookie-consent'
export const optionalCookies = ['functional', 'analytics'] as const

export type CookieConsent = Record<(typeof optionalCookies)[number], boolean>

export const allAccepted: CookieConsent = { functional: true, analytics: true }
export const allRejected: CookieConsent = {
  functional: false,
  analytics: false,
}

function isCookieConsent(value: unknown): value is CookieConsent {
  const consent = value as Partial<CookieConsent> | null
  return optionalCookies.every((id) => typeof consent?.[id] === 'boolean')
}

export function readCookieConsent(): CookieConsent | null {
  try {
    const saved = localStorage.getItem(storageKey)
    if (!saved) return null

    const consent: unknown = JSON.parse(saved)
    if (isCookieConsent(consent)) {
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
