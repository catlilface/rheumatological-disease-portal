type Theme = 'light'

export function applyTheme(theme: Theme = 'light') {
  document.documentElement.dataset.theme = theme
}
