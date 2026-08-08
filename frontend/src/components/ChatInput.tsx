import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

interface Props {
  onSend: (text: string) => void
  disabled: boolean
  placeholder: string
}

export const ChatInput = forwardRef<HTMLTextAreaElement, Props>(function ChatInput(
  { onSend, disabled, placeholder },
  forwardedRef,
) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(forwardedRef, () => textareaRef.current as HTMLTextAreaElement)

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 border-t border-line bg-surface p-2.5 dark:border-line-dark dark:bg-surface-dark">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={1}
        className="max-h-32 min-h-9 flex-1 resize-none rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none disabled:opacity-50 dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark dark:placeholder:text-ink-faint-dark dark:focus:border-accent-dark dark:focus:ring-accent-dark"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="shrink-0 rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-accent-dark dark:text-paper-dark"
      >
        Send
      </button>
    </div>
  )
})
