import type { ReactNode } from 'react'

export interface TabDef {
  id: string
  label: string
  disabled?: boolean
}

interface Props {
  tabs: TabDef[]
  active: string
  onChange: (id: string) => void
  children: ReactNode
}

export function Tabs({ tabs, active, onChange, children }: Props) {
  return (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div
        role="tablist"
        className="flex shrink-0 gap-1 border-b border-line px-3 pt-2 dark:border-line-dark"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={active === tab.id}
            disabled={tab.disabled}
            onClick={() => onChange(tab.id)}
            className={[
              'rounded-t-md border-x border-t px-3 py-1.5 font-mono text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40',
              active === tab.id
                ? 'border-line bg-surface text-ink dark:border-line-dark dark:bg-surface-dark dark:text-ink-dark'
                : 'border-transparent text-ink-muted hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark',
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        key={active}
        className="min-h-0 flex-1 animate-fade-in overflow-y-auto bg-surface dark:bg-surface-dark"
      >
        {children}
      </div>
    </div>
  )
}
