import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, type BundleSummary } from '../api'
import { useI18n } from '../i18n'
import { useUser } from '../user'
import { ErrorBox } from '../ui'

export default function NewProposal() {
  const { t } = useI18n()
  const { name } = useUser()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [bundles, setBundles] = useState<BundleSummary[]>()
  const [bundle, setBundle] = useState(params.get('bundle') ?? '')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.bundles().then((bs) => {
      setBundles(bs)
      setBundle((cur) => cur || bs[0]?.slug || '')
    }, setError)
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const p = await api.createProposal({ bundle, title, text, submitted_by: name })
      navigate(`/proposals/${p.id}`)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  if (bundles && bundles.length === 0) {
    return (
      <section>
        <h1>{t('new.title')}</h1>
        <p><Link to="/bundles">{t('new.noBundles')}</Link></p>
      </section>
    )
  }

  return (
    <section>
      <h1>{t('new.title')}</h1>
      <ErrorBox error={error} />
      <form className="form" onSubmit={submit}>
        <label>
          {t('new.bundle')}
          <select value={bundle} onChange={(e) => setBundle(e.target.value)} required>
            {bundles?.map((b) => <option key={b.slug} value={b.slug}>{b.name}</option>)}
          </select>
        </label>
        <label>
          {t('new.proposalTitle')}
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        <label>
          {t('new.text')}
          <span className="hint">{t('new.textHint')}</span>
          <textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} required />
        </label>
        <div className="actions">
          <button className="primary" disabled={busy || !bundle}>{t('new.submit')}</button>
        </div>
      </form>
    </section>
  )
}
