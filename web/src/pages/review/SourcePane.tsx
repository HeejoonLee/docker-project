import { useEffect, useState } from 'react'
import { api, type Proposal } from '../../api'
import { useI18n } from '../../i18n'

/** The Proposal's Source, read-only, shown beside the Article change it informed. */
export function SourcePane({ p, onClose }: { p: Proposal; onClose: () => void }) {
  const { t } = useI18n()
  const src = p.source
  const [text, setText] = useState<string>()

  // The proposal only carries a preview; load the full extracted text for reading side by side.
  useEffect(() => {
    if (!src || src.media === 'image') return
    let live = true
    fetch(api.sourceUrl(p.id, 'text.md'))
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(res.statusText))))
      .then((body) => { if (live) setText(body) }, () => { /* keep the preview */ })
    return () => { live = false }
  }, [p.id, src])

  if (!src) return null
  return (
    <div className="source-pane">
      <div className="pane-toolbar">
        <span className="pane-toolbar-title" title={src.filename || src.url || src.title}>
          {t('proposal.source')}: {t(`proposal.sourceKind.${src.kind}`)} · {src.filename || src.url || src.title}
          {src.pages ? ` · ${t('proposal.sourcePages', { count: String(src.pages) })}` : ''}
        </span>
        <a href={api.sourceUrl(p.id, src.original)} target="_blank" rel="noreferrer">{t('proposal.sourceOriginal')} ↗</a>
        <button className="icon-button" onClick={onClose} title={t('review.hideSource')}>✕</button>
      </div>
      <div className="source-pane-body">
        {p.targets.length > 0 && <p className="muted small">{t('proposal.targets')}: {p.targets.map((x) => <code key={x} className="path"> {x}</code>)}</p>}
        {src.url && <p className="small"><a href={src.url} target="_blank" rel="noreferrer">{src.url}</a></p>}
        {src.warnings.map((w, i) => <p key={i} className="notice">{w}</p>)}
        {src.media === 'image' ? (
          <img className="source-image" src={api.sourceUrl(p.id, src.original)} alt={src.filename} />
        ) : (
          <pre className="source-text">{text ?? src.preview}</pre>
        )}
      </div>
    </div>
  )
}
