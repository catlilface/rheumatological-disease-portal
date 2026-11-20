import { useEffect, useId, useRef, useState } from 'react'
import { t } from '@shared/i18n'
import { optionalCookies, type CookieConsent } from '../model/consent'

type CookieOptionProps = {
  id: keyof CookieConsent
  checked: boolean
  onChange: (checked: boolean) => void
}

function CookieOption({ id, checked, onChange }: CookieOptionProps) {
  const labelId = useId()
  const descriptionId = `${labelId}-description`

  return (
    <label>
      <input
        type="checkbox"
        checked={checked}
        aria-labelledby={labelId}
        aria-describedby={descriptionId}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <strong id={labelId}>{t(`cookies.${id}.label`)}</strong>
        <br />
        <span id={descriptionId}>{t(`cookies.${id}.description`)}</span>
      </span>
    </label>
  )
}

type CookieSettingsProps = {
  initialConsent: CookieConsent
  onSave: (consent: CookieConsent) => void
}

export function CookieSettings({
  initialConsent,
  onSave,
}: CookieSettingsProps) {
  const [selection, setSelection] = useState(initialConsent)
  const settings = useRef<HTMLFieldSetElement>(null)

  useEffect(() => {
    settings.current?.focus()
  }, [])

  return (
    <fieldset className="cookie-notice__settings" ref={settings} tabIndex={-1}>
      <legend>{t('cookies.optional')}</legend>
      {optionalCookies.map((id) => (
        <CookieOption
          key={id}
          id={id}
          checked={selection[id]}
          onChange={(checked) =>
            setSelection((current) => ({ ...current, [id]: checked }))
          }
        />
      ))}
      <button type="button" onClick={() => onSave(selection)}>
        {t('cookies.save')}
      </button>
    </fieldset>
  )
}
