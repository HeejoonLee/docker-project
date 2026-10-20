import { createContext, useContext, useState, type ReactNode } from 'react'
import en from './locales/en.json'
import ko from './locales/ko.json'

// To add a language: drop a JSON file into src/locales/ and register it here.
export const LOCALES: Record<string, { label: string; messages: Record<string, string> }> = {
  en: { label: 'English', messages: en },
  ko: { label: '한국어', messages: ko },
}

type I18n = { lang: string; setLang: (l: string) => void; t: (key: string, vars?: Record<string, string>) => string }
const Ctx = createContext<I18n | null>(null)

function readLang(): string {
  try {
    const saved = localStorage.getItem('stonepedia.lang')
    if (saved && LOCALES[saved]) return saved
  } catch { /* storage unavailable */ }
  return navigator.language.startsWith('ko') ? 'ko' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState(readLang)
  const setLang = (l: string) => {
    setLangState(l)
    try { localStorage.setItem('stonepedia.lang', l) } catch { /* ignore */ }
  }
  const t = (key: string, vars?: Record<string, string>) => {
    let s = LOCALES[lang].messages[key] ?? LOCALES.en.messages[key] ?? key
    for (const [k, v] of Object.entries(vars ?? {})) s = s.replace(`{${k}}`, v)
    return s
  }
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useI18n outside I18nProvider')
  return ctx
}
