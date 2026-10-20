import { createContext, useContext, useState, type ReactNode } from 'react'

type User = { name: string; setName: (n: string) => void }
const Ctx = createContext<User | null>(null)

function readName(): string {
  try { return localStorage.getItem('stonepedia.name') ?? '' } catch { return '' }
}

export function UserProvider({ children }: { children: ReactNode }) {
  const [name, setNameState] = useState(readName)
  const setName = (n: string) => {
    setNameState(n)
    try { localStorage.setItem('stonepedia.name', n) } catch { /* ignore */ }
  }
  return <Ctx.Provider value={{ name, setName }}>{children}</Ctx.Provider>
}

export function useUser(): User {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useUser outside UserProvider')
  return ctx
}
