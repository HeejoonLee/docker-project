import { useState, type FormEvent } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { useConfig } from './config'
import { LOCALES, useI18n } from './i18n'
import BundlePage from './pages/BundlePage'
import Bundles from './pages/Bundles'
import Inbox from './pages/Inbox'
import NewProposal from './pages/NewProposal'
import ProposalPage from './pages/ProposalPage'
import SettingsPage from './pages/SettingsPage'
import { useUser } from './user'

export default function App() {
  const { name } = useUser()
  return (
    <BrowserRouter>
      <Header />
      <main>
        {!name ? (
          <NamePrompt />
        ) : (
          <Routes>
            <Route path="/" element={<Inbox />} />
            <Route path="/new" element={<NewProposal />} />
            <Route path="/proposals/:id" element={<ProposalPage />} />
            <Route path="/bundles" element={<Bundles />} />
            <Route path="/bundles/:slug" element={<BundlePage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        )}
      </main>
    </BrowserRouter>
  )
}

function Header() {
  const { t, lang, setLang } = useI18n()
  const { name, setName } = useUser()
  const config = useConfig()
  return (
    <header className="topbar">
      <NavLink to="/" className="brand">Stonepedia</NavLink>
      <nav>
        <NavLink to="/" end>{t('nav.inbox')}</NavLink>
        <NavLink to="/new">{t('nav.new')}</NavLink>
        <NavLink to="/bundles">{t('nav.bundles')}</NavLink>
        <NavLink to="/settings">{t('nav.settings')}</NavLink>
      </nav>
      <div className="topbar-right">
        {config && <a href={config.temporal_ui_url} target="_blank" rel="noreferrer">{t('nav.temporal')} ↗</a>}
        <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
          {Object.entries(LOCALES).map(([code, l]) => <option key={code} value={code}>{l.label}</option>)}
        </select>
        {name && <button className="link" title={t('user.change')} onClick={() => setName('')}>{name}</button>}
      </div>
    </header>
  )
}

function NamePrompt() {
  const { t } = useI18n()
  const { setName } = useUser()
  const [value, setValue] = useState('')
  const save = (e: FormEvent) => {
    e.preventDefault()
    if (value.trim()) setName(value.trim())
  }
  return (
    <form className="form card narrow" onSubmit={save}>
      <label>
        {t('user.prompt')}
        <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder={t('user.placeholder')} />
      </label>
      <div className="actions"><button className="primary">{t('user.save')}</button></div>
    </form>
  )
}
