interface Props {
  role: 'user' | 'assistant'
  children: React.ReactNode
  tone?: 'default' | 'error'
}

export function MessageBubble({ role, children, tone = 'default' }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap sm:max-w-[70%]',
          isUser
            ? 'rounded-br-sm bg-indigo-600 text-white'
            : tone === 'error'
              ? 'rounded-bl-sm bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'
              : 'rounded-bl-sm bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100',
        ].join(' ')}
      >
        {children}
      </div>
    </div>
  )
}
