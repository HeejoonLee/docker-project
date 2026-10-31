import type { KeyboardEvent } from 'react'

/** Keyboard handling for a message box: Ctrl/Cmd+Enter sends, Esc cancels when it can. */
export function sendKeys(send: () => void, cancel?: () => void) {
  return (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      send()
    } else if (e.key === 'Escape' && cancel) {
      e.preventDefault()
      cancel()
    }
  }
}
