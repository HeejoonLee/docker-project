import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, MAX_SOURCES, type ArticleSummary, type BundleSummary, type NewSource } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox } from '../ui'
import { useUser } from '../user'

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.html,.htm,.txt,.md,.csv,.json,.yaml,.yml,.xml,.log,image/*'

type Row = NewSource & { key: number }

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

export default function NewProposal() {
  const { t } = useI18n()
  const { name } = useUser()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [bundles, setBundles] = useState<BundleSummary[]>()
  const [bundle, setBundle] = useState(params.get('bundle') ?? '')
  const [rows, setRows] = useState<Row[]>([])
  const nextKey = useRef(1)
  const [notice, setNotice] = useState('')
  const [requestText, setRequestText] = useState('')
  const [targets, setTargets] = useState<string[]>([])
  const [useReference, setUseReference] = useState(false)
  const [title, setTitle] = useState('')
  const [detail, setDetail] = useState<{ bundle: string; articles: ArticleSummary[]; referenceDir: string }>()
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const current = detail?.bundle === bundle ? detail : undefined
  const articles = current?.articles ?? []
  const referenceDir = current?.referenceDir ?? ''

  useEffect(() => {
    api.bundles().then((bs) => {
      setBundles(bs)
      setBundle((cur) => cur || bs[0]?.slug || '')
    }, setError)
  }, [])

  useEffect(() => {
    if (!bundle) return
    api.bundle(bundle).then((b) => setDetail({ bundle, articles: b.articles, referenceDir: b.reference_dir }), setError)
  }, [bundle])

  const add = (items: NewSource[]) => {
    setRows((cur) => [...cur, ...items.map((s) => ({ ...s, key: nextKey.current++ }))])
  }

  const addFiles = (files: File[]) => {
    const skipped: string[] = []
    const fresh: NewSource[] = []
    for (const file of files) {
      const known = [...rows, ...fresh].some((r) => r.kind === 'file' && r.file.name === file.name && r.file.size === file.size)
      if (known) skipped.push(file.name)
      else fresh.push({ kind: 'file', file })
    }
    const room = MAX_SOURCES - rows.length
    if (fresh.length > room) setNotice(t('new.tooMany', { max: String(MAX_SOURCES) }))
    else setNotice(skipped.length ? t('new.duplicateFile', { names: skipped.join(', ') }) : '')
    add(fresh.slice(0, Math.max(room, 0)))
  }

  const update = (key: number, change: Partial<Row>) =>
    setRows((cur) => cur.map((r) => (r.key === key ? ({ ...r, ...change } as Row) : r)))
  const remove = (key: number) => {
    setRows((cur) => cur.filter((r) => r.key !== key))
    setNotice('')
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) addFiles([...e.dataTransfer.files])
  }

  const linkCounts = new Map<string, number>()
  for (const r of rows) if (r.kind === 'link' && r.url.trim()) linkCounts.set(r.url.trim(), (linkCounts.get(r.url.trim()) ?? 0) + 1)
  const isDuplicateLink = (r: Row) => r.kind === 'link' && (linkCounts.get(r.url.trim()) ?? 0) > 1
  const hasDuplicates = rows.some(isDuplicateLink)
  const full = rows.length >= MAX_SOURCES
  const empty = rows.length === 0 && !requestText.trim()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const p = await api.createProposal({
        bundle, title, submitted_by: name,
        sources: rows.map(({ key: _key, ...s }) => s),
        request: requestText,
        targets: requestText.trim() ? targets : [],
        use_reference: useReference && !!referenceDir,
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
      <form className="form new-proposal" onSubmit={submit}>
        <label>
          {t('new.bundle')}
          <select value={bundle} onChange={(e) => { setBundle(e.target.value); setTargets([]); setUseReference(false) }} required>
            {bundles?.map((b) => <option key={b.slug} value={b.slug}>{b.name}</option>)}
          </select>
        </label>

        <fieldset className="np-block">
          <legend>{t('new.sources')} <span className="np-count">{rows.length}/{MAX_SOURCES}</span></legend>
          <p className="hint">{t('new.sourcesHint')}</p>
          <div
            className={`source-list${dragging ? ' dragging' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {rows.length === 0 && <div className="source-empty">{t('new.sourcesEmpty')}</div>}
            {rows.map((r, i) => (
              <div className="source-row" key={r.key}>
                <span className={`source-kind kind-${r.kind}`}>{i + 1} · {t(`new.kind.${r.kind}`)}</span>
                <div className="source-main">
                  {r.kind === 'text' && (
                    <textarea
                      rows={5} value={r.text} required autoFocus={!r.text}
                      placeholder={t('new.textHint')}
                      onChange={(e) => update(r.key, { text: e.target.value })}
                    />
                  )}
                  {r.kind === 'link' && (
                    <>
                      <input
                        type="url" value={r.url} required autoFocus={!r.url} placeholder="http://"
                        aria-invalid={isDuplicateLink(r)}
                        onChange={(e) => update(r.key, { url: e.target.value })}
                      />
                      {isDuplicateLink(r) && <span className="field-error">{t('new.duplicateLink')}</span>}
                    </>
                  )}
                  {r.kind === 'file' && (
                    <div className="source-file">
                      <span className="source-file-name">{r.file.name}</span>
                      <span className="muted small">{formatSize(r.file.size)}</span>
                    </div>
                  )}
                  <input
                    className="source-title" value={r.title ?? ''} placeholder={t('new.sourceTitle')}
                    onChange={(e) => update(r.key, { title: e.target.value })}
                  />
                </div>
                <button type="button" className="icon-button" title={t('new.removeSource')} aria-label={t('new.removeSource')} onClick={() => remove(r.key)}>✕</button>
              </div>
            ))}
          </div>
          <div className="actions">
            <button type="button" disabled={full} onClick={() => add([{ kind: 'text', text: '' }])}>+ {t('new.kind.text')}</button>
            <button type="button" disabled={full} onClick={() => fileInput.current?.click()}>+ {t('new.addFiles')}</button>
            <button type="button" disabled={full} onClick={() => add([{ kind: 'link', url: '' }])}>+ {t('new.kind.link')}</button>
            <input
              ref={fileInput} type="file" multiple hidden accept={ACCEPT}
              onChange={(e) => { addFiles([...(e.target.files ?? [])]); e.target.value = '' }}
            />
            {notice && <span className="hint">{notice}</span>}
          </div>
          <p className="hint">{t('new.fileHint')} {t('new.linkHint')}</p>
        </fieldset>

        <fieldset className="np-block">
          <legend>{t('new.request')}</legend>
          <label>
            <span className="hint">{t('new.requestHint')}</span>
            <textarea rows={4} value={requestText} onChange={(e) => setRequestText(e.target.value)} />
          </label>
          {requestText.trim() && articles.length > 0 && (
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
          {referenceDir && (
            <label className="check">
              <input type="checkbox" checked={useReference} onChange={(e) => setUseReference(e.target.checked)} />
              <span>{t('new.useReference', { path: referenceDir })}</span>
            </label>
          )}
          {useReference && rows.length === 0 && !requestText.trim() && <span className="hint">{t('new.codeFocus')}</span>}
        </fieldset>

        <label>
          {t('new.titleOptional')}
          <span className="hint">{t('new.titleHint')}</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <div className="actions">
          <button className="primary" disabled={busy || !bundle || empty || hasDuplicates}>
            {busy ? t('new.uploading') : t('new.submit')}
          </button>
          {empty && <span className="hint">{t('new.needSomething')}</span>}
        </div>
      </form>
    </section>
  )
}
