import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox, formatTime } from '../ui'
import { usePoll } from '../usePoll'

export default function Bundles() {
  const { t } = useI18n()
  const bundles = usePoll(api.bundles, 'bundles', 5000)
  const [open, setOpen] = useState(false)
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [language, setLanguage] = useState('ko')
  const [error, setError] = useState<unknown>()

  const create = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const b = await api.createBundle({ slug, name: name || slug, language })
      bundles.setData([...(bundles.data ?? []), b])
      setOpen(false)
      setSlug('')
      setName('')
      setError(undefined)
    } catch (err) {
      setError(err)
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
          <label>
            {t('bundles.slug')}
            <span className="hint">{t('bundles.slugHint')}</span>
            <input value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase())} pattern="[a-z0-9][a-z0-9-]{0,62}" required />
          </label>
          <label>
            {t('bundles.name')}
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={slug} />
          </label>
          <label>
            {t('bundles.language')}
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="ko">한국어</option>
              <option value="en">English</option>
            </select>
          </label>
          <div className="actions">
            <button className="primary">{t('common.create')}</button>
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
            <span className="muted"> · {b.slug} · {b.language} {b.created_at && `· ${formatTime(b.created_at)}`}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
