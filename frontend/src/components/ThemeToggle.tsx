import { useTheme } from '@/lib/useTheme'

export function ThemeToggle() {
  const [theme, toggle] = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode (Ctrl/Cmd+J)`}
      className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  )
}
