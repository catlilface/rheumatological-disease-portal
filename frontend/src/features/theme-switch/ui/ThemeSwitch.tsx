import { useId } from 'react'
import { t } from '@shared/i18n'
import { themes, type Theme } from '../model/theme'

type ThemeSwitchProps = {
  theme: Theme
  canChange: boolean
  onChange: (theme: Theme) => void
}

export default function ThemeSwitch({
  theme,
  canChange,
  onChange,
}: ThemeSwitchProps) {
  const unavailableId = useId()
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
            if (nextTheme) onChange(nextTheme)
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
