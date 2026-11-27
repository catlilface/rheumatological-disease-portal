import type { Material } from '@shared/api/contracts'
import { t } from '@shared/i18n'

function sourceUrl(url: string) {
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:')
      return parsed.href
  } catch {
    return undefined
  }
}

export function ReviewedMaterial({ material }: { material: Material }) {
  return (
    <>
      <h1>{material.title}</h1>
      <p className="article__meta">
        {t('library.reviewer', { name: material.reviewer.display_name })}
      </p>
      <p className="material-text">{material.body_markdown}</p>
      <div>
        <h2>{t('library.sources')}</h2>
        <ul>
          {material.sources.map(({ url, title }, index) => {
            const href = sourceUrl(url)
            return (
              <li key={index}>
                {href ? (
                  <a href={href} rel="noreferrer">
                    {title}
                  </a>
                ) : (
                  title
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </>
  )
}
