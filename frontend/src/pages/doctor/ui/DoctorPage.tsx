import { bff } from '@shared/api/client'
import { useBffQuery } from '@shared/api/useBff'
import { RequestStatus } from '@shared/ui/RequestStatus'
import { ReviewedMaterial } from '@shared/ui/ReviewedMaterial'
import { t } from '@shared/i18n'

export function DoctorPage() {
  const { state, reload } = useBffQuery(bff.doctorRoute)
  return (
    <article className="article portal-flow">
      {state.status === 'success' ? (
        <ReviewedMaterial material={state.data} />
      ) : (
        <>
          <h1>{t('nav.doctor')}</h1>
          <RequestStatus {...state} onRetry={reload} />
        </>
      )}
    </article>
  )
}
