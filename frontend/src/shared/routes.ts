import type { ResultRef } from './api/contracts'

export function resultRoute({ result_id, version }: ResultRef) {
  return '/results/' + encodeURIComponent(result_id) + '/versions/' + version
}
