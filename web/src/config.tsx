import { useEffect, useState } from 'react'
import { api, type AppConfig } from './api'

let cached: Promise<AppConfig> | undefined

export function useConfig(): AppConfig | undefined {
  const [config, setConfig] = useState<AppConfig>()
  useEffect(() => {
    cached ??= api.config()
    cached.then(setConfig, () => { cached = undefined })
  }, [])
  return config
}
