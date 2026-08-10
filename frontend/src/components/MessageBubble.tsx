interface Props {
  role: 'user' | 'assistant'
  children: React.ReactNode
  tone?: 'default' | 'error'
}

export function MessageBubble({ role, children, tone = 'default' }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex w-full animate-fade-in ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[90%] rounded-xl px-3.5 py-2.5 text-sm whitespace-pre-wrap',
          isUser
            ? 'rounded-br-sm bg-ink text-paper dark:bg-ink-dark dark:text-paper-dark'
            : tone === 'error'
              ? 'rounded-bl-sm border border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300'
              : 'rounded-bl-sm border border-line bg-paper text-ink dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark',
        ].join(' ')}
      >
        {children}
      </div>
    </div>
  )
}
