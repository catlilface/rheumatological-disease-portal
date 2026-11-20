import { useId, useLayoutEffect, useRef, useState } from 'react'
import { t } from '@shared/i18n'
import {
  readTheme,
  syncThemePreference,
  themes,
  type Theme,
} from '../model/theme'

export default function ThemeSwitch({ remember }: { remember: boolean }) {
  const [{ theme, canChange }, setSelection] = useState(() =>
    readTheme(remember),
  )
  const appliedTheme = useRef<Theme>('auto')
  const unavailableId = useId()

  useLayoutEffect(() => {
    if (canChange && !syncThemePreference(theme, remember)) {
      setSelection({ theme: appliedTheme.current, canChange: false })
      return
    }

    document.documentElement.dataset.theme = theme
    appliedTheme.current = theme
  }, [theme, remember, canChange])

  return (
    <div>
      <label className="theme-select">
        {t('theme.label')}
        <select
          disabled={!canChange}
          aria-describedby={canChange ? undefined : unavailableId}
          value={theme}
          onChange={(event) => {
            const nextTheme = themes.find(
              (option) => option === event.target.value,
            )
            if (nextTheme) setSelection({ theme: nextTheme, canChange: true })
          }}
        >
          {themes.map((option) => (
            <option key={option} value={option}>
              {t(`theme.${option}`)}
            </option>
          ))}
        </select>
      </label>
      {!canChange && <p id={unavailableId}>{t('theme.unavailable')}</p>}
    </div>
  )
}
