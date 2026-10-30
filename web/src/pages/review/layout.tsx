import { useCallback, useState, type PointerEvent as ReactPointerEvent } from 'react'

/** State that survives reloads, kept in localStorage under `stonepedia.<key>`. */
export function useStored<T>(key: string, initial: T) {
  const storageKey = `stonepedia.${key}`
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      return saved === null ? initial : (JSON.parse(saved) as T)
    } catch {
      return initial
    }
  })
  const set = useCallback((next: T) => {
    setValue(next)
    try { localStorage.setItem(storageKey, JSON.stringify(next)) } catch { /* storage unavailable */ }
  }, [storageKey])
  return [value, set] as const
}

/**
 * A drag handle between two panes. `value` is the size of the pane it resizes;
 * `invert` is for panes that sit after the handle (dragging left makes them wider).
 */
export function Splitter({ axis, value, onChange, min, max, invert = false }: {
  axis: 'x' | 'y'
  value: number
  onChange: (size: number) => void
  min: number
  max: number
  invert?: boolean
}) {
  const start = (e: ReactPointerEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    const origin = axis === 'x' ? e.clientX : e.clientY
    const move = (ev: PointerEvent) => {
      const delta = (axis === 'x' ? ev.clientX : ev.clientY) - origin
      onChange(Math.round(Math.min(max, Math.max(min, value + (invert ? -delta : delta)))))
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      document.body.classList.remove('resizing-x', 'resizing-y')
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    document.body.classList.add(`resizing-${axis}`)
  }
  return (
    <div
      className={`splitter splitter-${axis}`}
      role="separator"
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      onPointerDown={start}
    />
  )
}
