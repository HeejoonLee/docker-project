import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type NewBundle } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox, formatTime } from '../ui'
import { usePoll } from '../usePoll'

const EMPTY: NewBundle = { slug: '', name: '', language: 'ko', id_prefix: '', clone_url: '', branch: '', root: '.', remote_url: '' }

export default function Bundles() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const bundles = usePoll(api.bundles, 'bundles', 5000)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'empty' | 'clone'>('empty')
  const [form, setForm] = useState<NewBundle>(EMPTY)
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)
  const set = (patch: Partial<NewBundle>) => setForm({ ...form, ...patch })

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      const body = mode === 'empty'
        ? { ...form, clone_url: '', branch: '', root: '.', name: form.name || form.slug }
        : { ...form, remote_url: '', name: form.name || form.slug }
      const b = await api.createBundle(body)
      navigate(`/bundles/${b.slug}`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>{t('bundles.title')}</h1>
        {!open && <button className="primary" onClick={() => setOpen(true)}>{t('bundles.new')}</button>}
      </div>
      {open && (
        <form className="form card" onSubmit={create}>
          <ErrorBox error={error} />
          <div className="segmented">
            {(['empty', 'clone'] as const).map((m) => (
              <button type="button" key={m} className={mode === m ? 'active' : ''} onClick={() => setMode(m)}>{t(`bundles.mode.${m}`)}</button>
            ))}
          </div>
          <label>
            {t('bundles.slug')}
            <span className="hint">{t('bundles.slugHint')}</span>
            <input value={form.slug} onChange={(e) => set({ slug: e.target.value.toLowerCase() })} pattern="[a-z0-9][a-z0-9\-]{0,62}" required />
          </label>
          <label>
            {t('bundles.name')}
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder={form.slug} />
          </label>
          {mode === 'clone' && (
            <>
              <label>
                {t('bundles.cloneUrl')}
                <span className="hint">{t('bundles.cloneUrlHint')}</span>
                <input value={form.clone_url} onChange={(e) => set({ clone_url: e.target.value })} required />
              </label>
              <label>
                {t('bundles.branch')}
                <span className="hint">{t('bundles.branchHint')}</span>
                <input value={form.branch} onChange={(e) => set({ branch: e.target.value })} />
              </label>
              <label>
                {t('bundles.root')}
                <span className="hint">{t('bundles.rootHint')}</span>
                <input value={form.root} onChange={(e) => set({ root: e.target.value })} />
              </label>
            </>
          )}
          <label>
            {t('bundles.language')}
            <select value={form.language} onChange={(e) => set({ language: e.target.value })}>
              <option value="ko">한국어</option>
              <option value="en">English</option>
            </select>
          </label>
          <label>
            {t('bundles.idPrefix')}
            <span className="hint">{t('bundles.idPrefixHint')}</span>
            <input value={form.id_prefix} onChange={(e) => set({ id_prefix: e.target.value })} />
          </label>
          {mode === 'empty' && (
            <label>
              {t('bundles.remote')}
              <span className="hint">{t('bundles.remoteHint')}</span>
              <input value={form.remote_url} onChange={(e) => set({ remote_url: e.target.value })} />
            </label>
          )}
          <div className="actions">
            <button className="primary" disabled={busy}>{busy ? t('bundles.creating') : t('common.create')}</button>
            <button type="button" onClick={() => setOpen(false)}>{t('common.cancel')}</button>
          </div>
        </form>
      )}
      <ErrorBox error={bundles.error} />
      {bundles.data?.length === 0 && !open && <p className="muted">{t('bundles.empty')}</p>}
      <ul className="bundle-list">
        {bundles.data?.map((b) => (
          <li key={b.slug} className="card">
            <Link to={`/bundles/${b.slug}`}><strong>{b.name}</strong></Link>
            <div className="muted small">{b.slug} · {b.language}{b.created_at && ` · ${formatTime(b.created_at)}`}</div>
          </li>
        ))}
      </ul>
    </section>
  )
}
