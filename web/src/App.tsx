import { useState, type FormEvent } from 'react'
import { BrowserRouter, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useConfig } from './config'
import { BrandMark } from './BrandMark'
import { LOCALES, useI18n } from './i18n'
import BundlePage from './pages/BundlePage'
import Bundles from './pages/Bundles'
import Inbox from './pages/Inbox'
import MaintenancePage from './pages/MaintenancePage'
import NewProposal from './pages/NewProposal'
import ProposalPage from './pages/ProposalPage'
import SettingsPage from './pages/SettingsPage'
import Welcome from './pages/Welcome'
import './welcome.css'
import { useUser } from './user'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route element={<Workspace />}>
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/new" element={<NewProposal />} />
          <Route path="/proposals/:id" element={<ProposalPage />} />
          <Route path="/bundles" element={<Bundles />} />
          <Route path="/bundles/:slug" element={<BundlePage />} />
          <Route path="/maintenance" element={<MaintenancePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

function Workspace() {
  const { name } = useUser()
  return <><Header /><main>{name ? <Outlet /> : <NamePrompt />}</main></>
}

function Header() {
  const { t, lang, setLang } = useI18n()
  const { name, setName } = useUser()
  const config = useConfig()
  const { pathname } = useLocation()
  const inInbox = pathname === '/inbox' || pathname.startsWith('/proposals/')
  return (
    <header className="topbar">
      <NavLink to="/" className="brand" aria-label="Stonepedia"><BrandMark /><span>Stonepedia<span className="brand-dot">.</span></span></NavLink>
      <nav aria-label={t('nav.workspace')}>
        <NavLink to="/" end>{t('nav.home')}</NavLink>
        <NavLink to="/inbox" className={() => (inInbox ? 'active' : '')}>{t('nav.inbox')}</NavLink>
        <NavLink to="/new">{t('nav.new')}</NavLink>
        <NavLink to="/bundles">{t('nav.bundles')}</NavLink>
        <NavLink to="/maintenance">{t('nav.maintenance')}</NavLink>
        <NavLink to="/settings">{t('nav.settings')}</NavLink>
      </nav>
      <div className="topbar-right">
        {config && <a className="ghost" href={config.temporal_ui_url} target="_blank" rel="noreferrer">{t('nav.temporal')} ↗</a>}
        <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
          {Object.entries(LOCALES).map(([code, l]) => <option key={code} value={code}>{l.label}</option>)}
        </select>
        {name && (
          <button className="user-chip" title={t('user.change')} onClick={() => setName('')}>
            <span className="avatar">{name.slice(0, 1).toUpperCase()}</span>{name}
          </button>
        )}
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
