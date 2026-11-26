import { BffError } from '@shared/api/client'
import { t } from '@shared/i18n'

export function RequestStatus({
  status,
  error,
  onRetry,
}: {
  status: 'idle' | 'loading' | 'pending' | 'success' | 'error'
  error?: unknown
  onRetry?: () => void
}) {
  if (status === 'loading') return <p role="status">{t('api.loading')}</p>
  if (status === 'pending') return <p role="status">{t('api.pending')}</p>
  if (status !== 'error') return null
  const code = error instanceof BffError ? error.code : undefined
  const message =
    code === 'SESSION_REQUIRED'
      ? t('api.sessionRequired')
      : code === 'NOT_FOUND'
        ? t('api.notFound')
        : code === 'SESSION_VERSION_CONFLICT'
          ? t('api.versionConflict')
          : code === 'DISCLAIMER_VERSION_MISMATCH'
            ? t('api.disclaimerChanged')
            : t('api.error')
  return (
    <div>
      <p role="alert">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          {t('api.retry')}
        </button>
      )}
    </div>
  )
}
