import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, type ArticleSummary, type BundleSummary, type SourceKind } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox } from '../ui'
import { useUser } from '../user'

const KINDS: SourceKind[] = ['text', 'file', 'link', 'request', 'code']

export default function NewProposal() {
  const { t } = useI18n()
  const { name } = useUser()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [bundles, setBundles] = useState<BundleSummary[]>()
  const [bundle, setBundle] = useState(params.get('bundle') ?? '')
  const [kind, setKind] = useState<SourceKind>((params.get('kind') as SourceKind) || 'text')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File>()
  const [articles, setArticles] = useState<ArticleSummary[]>([])
  const [reference, setReference] = useState<{ bundle: string; dir: string }>()
  const referenceDir = reference?.bundle === bundle ? reference.dir : ''
  const [targets, setTargets] = useState<string[]>([])
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.bundles().then((bs) => {
      setBundles(bs)
      setBundle((cur) => cur || bs[0]?.slug || '')
    }, setError)
  }, [])

  useEffect(() => {
    if (!bundle || kind !== 'request') return
    api.bundle(bundle).then((b) => setArticles(b.articles), setError)
  }, [bundle, kind])

  useEffect(() => {
    if (!bundle) return
    api.bundle(bundle).then((b) => setReference({ bundle, dir: b.reference_dir }), setError)
  }, [bundle])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const p = await api.createProposal({
        bundle, kind, title, submitted_by: name,
        text: kind === 'text' || kind === 'request' || kind === 'code' ? text : undefined,
        url: kind === 'link' ? url : undefined,
        file: kind === 'file' ? file : undefined,
        targets: kind === 'request' ? targets : undefined,
      })
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

  const toggleTarget = (path: string) =>
    setTargets((cur) => (cur.includes(path) ? cur.filter((p) => p !== path) : [...cur, path]))

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

        <div className="segmented" role="tablist">
          {KINDS.map((k) => (
            <button type="button" key={k} role="tab" aria-selected={kind === k} className={kind === k ? 'active' : ''} onClick={() => setKind(k)}>
              {t(`new.kind.${k}`)}
            </button>
          ))}
        </div>

        {kind === 'text' && (
          <label>
            {t('new.text')}
            <span className="hint">{t('new.textHint')}</span>
            <textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} required />
          </label>
        )}
        {kind === 'file' && (
          <label>
            {t('new.file')}
            <span className="hint">{t('new.fileHint')}</span>
            <input
              type="file" required
              accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.txt,.md,.csv,.json,.yaml,.yml,.xml,.log,image/*"
              onChange={(e) => setFile(e.target.files?.[0])}
            />
          </label>
        )}
        {kind === 'link' && (
          <label>
            {t('new.link')}
            <span className="hint">{t('new.linkHint')}</span>
            <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://" required />
          </label>
        )}
        {kind === 'request' && (
          <>
            <label>
              {t('new.requestText')}
              <span className="hint">{t('new.requestHint')}</span>
              <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} required />
            </label>
            {articles.length > 0 && (
              <fieldset className="targets">
                <legend>{t('new.targets')}</legend>
                {articles.map((a) => (
                  <label key={a.path} className="check">
                    <input type="checkbox" checked={targets.includes(a.path)} onChange={() => toggleTarget(a.path)} />
                    <span>{a.title} <code className="path">{a.path}</code></span>
                  </label>
                ))}
              </fieldset>
            )}
          </>
        )}
        {kind === 'code' && (
          <label>
            {t('new.codeFocus')}
            <span className="hint">{referenceDir ? t('new.codeHint', { path: referenceDir }) : t('new.codeMissing')}</span>
            <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} required />
          </label>
        )}

        <label>
          {t('new.titleOptional')}
          <span className="hint">{t('new.titleHint')}</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <div className="actions">
          <button className="primary" disabled={busy || !bundle || (kind === 'code' && !referenceDir)}>{busy ? t('new.uploading') : t('new.submit')}</button>
        </div>
      </form>
    </section>
  )
}
