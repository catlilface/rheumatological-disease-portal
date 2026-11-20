import { ru } from './ru.ts'

export type MessageKey = keyof typeof ru

export function t(
  key: MessageKey,
  values: Record<string, string> = {},
): string {
  return ru[key].replace(
    /\{(\w+)\}/g,
    (placeholder, name: string) => values[name] ?? placeholder,
  )
}
