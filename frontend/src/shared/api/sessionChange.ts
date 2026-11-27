// Only an invalidation signal crosses tabs; neither credentials nor patient data do.
const events = new EventTarget()
const channel =
  typeof window.BroadcastChannel === 'function'
    ? new window.BroadcastChannel('portal-session-change')
    : undefined

export function notifySessionChange(allTabs = false) {
  events.dispatchEvent(new Event('change'))
  if (allTabs) channel?.postMessage(null)
}

export function onSessionChange(reload: () => void) {
  events.addEventListener('change', reload)
  channel?.addEventListener('message', reload)
  return () => {
    events.removeEventListener('change', reload)
    channel?.removeEventListener('message', reload)
  }
}
