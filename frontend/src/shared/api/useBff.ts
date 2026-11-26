import { useEffect, useRef, useState } from 'react'
import { BffError, type Command } from './client'

type RequestState<T> =
  | { status: 'idle' | 'loading' | 'pending' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: unknown }

export function useBffQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState<{
    load: typeof load
    attempt: number
    state: RequestState<T>
  }>()
  const state: RequestState<T> =
    settled?.load === load && settled.attempt === attempt
      ? settled.state
      : { status: 'loading' }
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setSettled({ load, attempt, state: { status: 'success', data } })
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setSettled({ load, attempt, state: { status: 'error', error } })
      },
    )
    return () => controller.abort()
  }, [load, attempt])
  return { state, reload: () => setAttempt((value) => value + 1) }
}

export function useBffCommand<T>() {
  const [state, setState] = useState<RequestState<T>>({ status: 'idle' })
  const active = useRef<AbortController | null>(null)
  const last = useRef<Command<T> | null>(null)

  useEffect(
    () => () => {
      active.current?.abort()
      active.current = null
    },
    [],
  )

  async function run(task: Command<T>) {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    last.current = task
    setState({ status: 'loading' })
    try {
      const data = await task(controller.signal, () => {
        if (!controller.signal.aborted) setState({ status: 'pending' })
      })
      if (!controller.signal.aborted) setState({ status: 'success', data })
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: 'error', error })
    } finally {
      if (active.current === controller) active.current = null
    }
  }
  const retryable =
    state.status === 'error' &&
    (!(state.error instanceof BffError) || state.error.retryable)
  return {
    state,
    busy: state.status === 'loading' || state.status === 'pending',
    retryable,
    run,
    retry: () => {
      if (last.current && retryable) void run(last.current)
    },
  }
}
