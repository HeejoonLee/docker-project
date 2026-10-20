import { useCallback, useEffect, useRef, useState } from 'react'

/** Load data now, then reload every `intervalMs` while `keepPolling(data)` is true. */
export function usePoll<T>(
  load: () => Promise<T>,
  key: string,
  intervalMs: number,
  keepPolling: (d: T | undefined) => boolean = () => true,
) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<unknown>()
  const loadRef = useRef(load)
  const keepRef = useRef(keepPolling)
  loadRef.current = load
  keepRef.current = keepPolling

  const reload = useCallback(
    () => loadRef.current().then((d) => { setData(d); setError(undefined) }, setError),
    [],
  )
  useEffect(() => { setData(undefined); reload() }, [key, reload])
  useEffect(() => {
    if (!keepRef.current(data)) return
    const id = setInterval(reload, intervalMs)
    return () => clearInterval(id)
  }, [data, reload, intervalMs])
  return { data, error, reload, setData }
}
