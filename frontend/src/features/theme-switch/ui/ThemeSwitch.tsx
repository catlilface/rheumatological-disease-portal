import './theme-switch.css'
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
  const groupName = useId()
  const unavailableId = `${groupName}-unavailable`

  return (
    <fieldset
      className="theme-switch"
      disabled={!canChange}
      aria-describedby={canChange ? undefined : unavailableId}
    >
      <legend>{t('theme.label')}</legend>
      <div className="theme-switch__options">
        {themes.map((option) => (
          <label className="theme-switch__option" key={option}>
            <input
              className="theme-switch__input"
              type="radio"
              name={groupName}
              value={option}
              checked={theme === option}
              onChange={() => onChange(option)}
            />
            <span>{t(`theme.${option}`)}</span>
          </label>
        ))}
      </div>
      {!canChange && (
        <p className="theme-switch__notice" id={unavailableId}>
          {t('theme.unavailable')}
        </p>
      )}
    </fieldset>
  )
}
