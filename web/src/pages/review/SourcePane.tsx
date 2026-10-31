import { useEffect, useState } from 'react'
import { api, type Proposal } from '../../api'
import { useI18n } from '../../i18n'
import { citedIds, itemLabel, proposalItems } from './sources'

/** The Proposal's Sources and Request, one tab each, read-only beside the Article change they informed. */
export function SourcePane({ p, selected, onSelect, onClose }: {
  p: Proposal
  selected: string | null
  onSelect: (id: string) => void
  onClose: () => void
}) {
  const { t } = useI18n()
  const items = proposalItems(p)
  const src = items.find((i) => i.id === selected) ?? items[0]
  const [text, setText] = useState<{ id: string; body: string }>()

  // A Source only carries a preview; load the full extracted text for reading side by side.
  useEffect(() => {
    if (!src || src.media === 'image') return
    let live = true
    fetch(api.sourceUrl(p.id, src.id, 'text.md'))
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(res.statusText))))
      .then((body) => { if (live) setText({ id: src.id, body }) }, () => { /* keep the preview */ })
    return () => { live = false }
  }, [p.id, src])

  if (!src) return null
  const kindLabel = (kind: string) => t(`proposal.sourceKind.${kind}`)
  const settled = p.state !== 'generating' && p.state !== 'failed'
  const cited = new Set(p.changes.filter((c) => c.decision !== 'discarded').flatMap((c) => citedIds(c.content, items)))
  const name = src.kind === 'request' || src.kind === 'audit' ? kindLabel(src.kind) : src.filename || src.url || src.title

  return (
    <div className="source-pane">
      <div className="pane-toolbar">
        <span className="pane-toolbar-title" title={name}>
          {kindLabel(src.kind)} · {name}
          {src.pages ? ` · ${t('proposal.sourcePages', { count: String(src.pages) })}` : ''}
        </span>
        <a href={api.sourceUrl(p.id, src.id, src.original)} target="_blank" rel="noreferrer">{t('proposal.sourceOriginal')} ↗</a>
        <button className="icon-button" onClick={onClose} title={t('review.hideSource')}>✕</button>
      </div>
      <nav className="source-tabs" aria-label={t('proposal.sources')}>
        {items.map((item) => {
          const uncited = settled && item.kind !== 'audit' && !cited.has(item.id)
          return (
            <button
              key={item.id}
              className={item.id === src.id ? 'active' : ''}
              title={item.title}
              onClick={() => onSelect(item.id)}
            >
              <span className="source-tab-num">{itemLabel(p, item, kindLabel)}</span>
              {item.kind !== 'request' && item.kind !== 'audit' && <span className="source-tab-title">{item.title}</span>}
              {uncited && <span className="badge uncited" title={t('proposal.uncitedHint')}>{t('proposal.uncited')}</span>}
            </button>
          )
        })}
        {(p.use_reference || p.reference_used) && <span className="source-tab-marker">{t('proposal.referenceConsulted')}</span>}
      </nav>
      <div className="source-pane-body">
        {src.kind === 'request' && p.targets.length > 0 && (
          <p className="muted small">{t('proposal.targets')}: {p.targets.map((x) => <code key={x} className="path"> {x}</code>)}</p>
        )}
        {src.url && <p className="small"><a href={src.url} target="_blank" rel="noreferrer">{src.url}</a></p>}
        {src.warnings.map((w, i) => <p key={i} className="notice">{w}</p>)}
        {src.media === 'image' ? (
          <img className="source-image" src={api.sourceUrl(p.id, src.id, src.original)} alt={src.filename} />
        ) : (
          <pre className="source-text">{text?.id === src.id ? text.body : src.preview}</pre>
        )}
      </div>
    </div>
  )
}
