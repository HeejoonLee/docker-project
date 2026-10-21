import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type ArticleChange, type Decision, type Proposal } from '../api'
import { useConfig } from '../config'
import { useI18n } from '../i18n'
import { DiffView } from '../diff'
import { ArticleView, Markdown } from '../markdown'
import { ErrorBox, StateBadge, formatTime } from '../ui'
import { usePoll } from '../usePoll'
import { useUser } from '../user'

const BUSY = new Set(['generating', 'committing'])

export default function ProposalPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const { name } = useUser()
  const config = useConfig()
  const { data: p, error, setData } = usePoll(() => api.proposal(id), id, 2000, (d) => !d || BUSY.has(d.state))
  const [actionError, setActionError] = useState<unknown>()
  const [feedback, setFeedback] = useState('')
  // Cards start collapsed when there are many, so the overview fits on screen.
  const [expanded, setExpanded] = useState<Set<string> | null>(null)

  const act = async (fn: () => Promise<Proposal>) => {
    try {
      setActionError(undefined)
      setData(await fn())
      return true
    } catch (err) {
      setActionError(err)
      return false
    }
  }

  if (!p) return error ? <ErrorBox error={error} /> : <p className="muted">{t('common.loading')}</p>
  const reviewable = p.state === 'awaiting_review'
  const allDecided = p.changes.every((c) => c.decision !== 'pending')
  const open = expanded ?? new Set(p.changes.length <= 2 ? p.changes.map((c) => c.id) : [])
  const toggle = (cid: string, force?: boolean) => {
    const next = new Set(open)
    if (force ?? !next.has(cid)) next.add(cid)
    else next.delete(cid)
    setExpanded(next)
  }
  const jump = (cid: string) => {
    toggle(cid, true)
    requestAnimationFrame(() => document.getElementById(`change-${cid}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
  const decided = p.changes.filter((c) => c.decision !== 'pending').length
  const temporalLink = config && `${config.temporal_ui_url}/namespaces/${config.namespace}/workflows/proposal-${p.id}`

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>{p.title}</h1>
          <p className="muted">
            {p.bundle} · {t('proposal.by', { name: p.submitted_by })} · <StateBadge state={p.state} />
            {p.runs > 0 && <> · {t('proposal.cost', { runs: String(p.runs), cost: p.cost_usd.toFixed(2) })}</>}
          </p>
        </div>
        {temporalLink && <a className="small" href={temporalLink} target="_blank" rel="noreferrer">{t('proposal.openTemporal')} ↗</a>}
      </div>

      <SourceCard p={p} />

      {p.state === 'generating' && <p className="notice working">{t('proposal.generating')}</p>}
      {p.state === 'committing' && <p className="notice working">{t('proposal.committing')}</p>}
      {p.state === 'done' && <p className="notice ok">{t('proposal.committed', { commit: (p.commit ?? '').slice(0, 8), name: p.reviewer ?? '' })}</p>}
      {p.state === 'discarded' && <p className="notice">{t('proposal.discardedAll', { name: p.reviewer ?? '' })}</p>}
      {p.error && <div className="error">{p.error}</div>}
      <ErrorBox error={actionError} />

      {p.summary && (
        <details className="summary" open={reviewable}>
          <summary>{t('proposal.summary')}</summary>
          <div className="summary-body"><Markdown text={p.summary} /></div>
        </details>
      )}

      {reviewable && p.changes.length === 0 && <p className="notice">{t('proposal.noChanges')}</p>}

      {p.changes.length > 0 && (
        <ChangeOverview
          changes={p.changes}
          open={open}
          onJump={jump}
          onAll={(on) => setExpanded(new Set(on ? p.changes.map((c) => c.id) : []))}
        />
      )}

      {p.changes.map((c, i) => (
        <ChangeCard
          key={c.id}
          change={c}
          index={i + 1}
          total={p.changes.length}
          open={open.has(c.id)}
          onToggle={() => toggle(c.id)}
          editable={reviewable}
          onDecide={(d) => act(() => api.decide(p.id, c.id, d))}
          onRevise={(text) => act(() => api.revise(p.id, c.id, text, name))}
          onEdit={(content) => act(() => api.edit(p.id, c.id, content, name))}
        />
      ))}

      {reviewable && (
        <div className="card feedback">
          <label>
            <strong>{t('proposal.feedbackTitle')}</strong>
            <span className="hint">{t('proposal.feedbackHint')}</span>
            <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
          </label>
          <div className="actions">
            <button
              disabled={!feedback.trim()}
              onClick={async () => { if (await act(() => api.feedback(p.id, feedback, name))) setFeedback('') }}
            >
              {t('proposal.feedbackSend')}
            </button>
          </div>
        </div>
      )}

      {reviewable && (
        <div className="submit-bar">
          <span className="muted">
            <strong>{t('proposal.decidedCount', { done: String(decided), total: String(p.changes.length) })}</strong> · {t('proposal.submitHint')}
          </span>
          <button className="primary" disabled={!allDecided} onClick={() => act(() => api.submit(p.id, name))}>
            {t('proposal.submit')}
          </button>
        </div>
      )}
    </section>
  )
}

function SourceCard({ p }: { p: Proposal }) {
  const { t } = useI18n()
  const src = p.source
  if (!src) return null
  return (
    <details className="source">
      <summary>
        {t('proposal.source')}: {t(`proposal.sourceKind.${src.kind}`)} · {src.filename || src.url || src.title}
        {src.pages ? ` · ${t('proposal.sourcePages', { count: String(src.pages) })}` : ''}
      </summary>
      {p.targets.length > 0 && <p className="muted">{t('proposal.targets')}: {p.targets.map((x) => <code key={x} className="path"> {x}</code>)}</p>}
      {src.warnings.map((w, i) => <p key={i} className="notice">{w}</p>)}
      <p className="small">
        <a href={api.sourceUrl(p.id, src.original)} target="_blank" rel="noreferrer">{t('proposal.sourceOriginal')} ↗</a>
        {' · '}
        <a href={api.sourceUrl(p.id, 'text.md')} target="_blank" rel="noreferrer">{t('proposal.sourceText')} ↗</a>
        {src.url && <>{' · '}<a href={src.url} target="_blank" rel="noreferrer">{src.url}</a></>}
      </p>
      {src.media === 'image' ? (
        <img className="source-image" src={api.sourceUrl(p.id, src.original)} alt={src.filename} />
      ) : (
        <pre>{src.preview}{src.text_chars > src.preview.length ? '\n…' : ''}</pre>
      )}
    </details>
  )
}

function ChangeOverview({ changes, open, onJump, onAll }: {
  changes: ArticleChange[]
  open: Set<string>
  onJump: (id: string) => void
  onAll: (expand: boolean) => void
}) {
  const { t } = useI18n()
  const count = (pred: (c: ArticleChange) => boolean) => changes.filter(pred).length
  const kinds = (['create', 'update', 'retire'] as const).map((k) => [k, count((c) => c.kind === k)] as const).filter(([, n]) => n > 0)
  const decisions = (['pending', 'accepted', 'discarded'] as const).map((d) => [d, count((c) => c.decision === d)] as const).filter(([, n]) => n > 0)
  return (
    <div className="card overview">
      <div className="overview-head">
        <h2>{t('proposal.overview', { count: String(changes.length) })}</h2>
        <span className="overview-counts">
          {kinds.map(([k, n]) => <span key={k} className={`kind kind-${k}`}>{t(`proposal.kind.${k}`)} {n}</span>)}
          <span className="muted">·</span>
          {decisions.map(([d, n]) => <span key={d} className={`badge decided-${d}`}>{t(`proposal.${d}`)} {n}</span>)}
        </span>
        <span className="overview-toggle small">
          <button className="link" onClick={() => onAll(true)} disabled={open.size === changes.length}>{t('proposal.expandAll')}</button>
          {' · '}
          <button className="link" onClick={() => onAll(false)} disabled={open.size === 0}>{t('proposal.collapseAll')}</button>
        </span>
      </div>
      <ol className="overview-list">
        {changes.map((c) => (
          <li key={c.id} className={`decision-${c.decision}${c.stale ? ' stale' : ''}`}>
            <button className="overview-row" onClick={() => onJump(c.id)}>
              <span className={`kind kind-${c.kind}`}>{t(`proposal.kind.${c.kind}`)}</span>
              <span className="overview-title">{c.title}</span>
              <code className="path">{c.path}</code>
              <span className={`badge decided-${c.decision}`}>{c.stale ? t('proposal.staleShort') : t(`proposal.${c.decision}`)}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

type Panel = 'none' | 'revise' | 'edit'

function ChangeCard({ change, index, total, open, onToggle, editable, onDecide, onRevise, onEdit }: {
  change: ArticleChange
  index: number
  total: number
  open: boolean
  onToggle: () => void
  editable: boolean
  onDecide: (d: Decision) => void
  onRevise: (feedback: string) => Promise<boolean>
  onEdit: (content: string) => Promise<boolean>
}) {
  const { t } = useI18n()
  const [tab, setTab] = useState<'preview' | 'diff' | 'source'>(change.kind === 'create' ? 'preview' : 'diff')
  const [panel, setPanel] = useState<Panel>('none')
  const [reviseText, setReviseText] = useState('')
  const [draft, setDraft] = useState(change.content)
  const pending = change.decision === 'pending'

  const openPanel = (next: Panel) => {
    setPanel(panel === next ? 'none' : next)
    if (next === 'edit') setDraft(change.content)
  }

  return (
    <article id={`change-${change.id}`} className={`change decision-${change.decision}${change.stale ? ' stale' : ''}${open ? '' : ' collapsed'}`}>
      <header>
        <div className="change-title">
          <button className="link fold" onClick={onToggle} aria-expanded={open} title={open ? t('proposal.collapse') : t('proposal.expand')}>
            {open ? '▾' : '▸'} <span className="muted small">{index} / {total}</span>
          </button>
          <span className={`kind kind-${change.kind}`}>{t(`proposal.kind.${change.kind}`)}</span>
          <div className="change-name">
            <strong>{change.title}</strong>
            <div>
              <code className="path">{change.path}</code>
              {change.edited_by && <span className="muted small"> · {t('proposal.editedBy', { name: change.edited_by })}</span>}
            </div>
          </div>
        </div>
        <div className="decide">
          {pending ? (
            editable && (
              <>
                <button className="primary" disabled={change.stale} onClick={() => onDecide('accepted')}>{t('proposal.accept')}</button>
                <button onClick={() => openPanel('revise')}>{t('proposal.revise')}</button>
                <button onClick={() => openPanel('edit')}>{t('proposal.edit')}</button>
                <button onClick={() => onDecide('discarded')}>{t('proposal.discard')}</button>
              </>
            )
          ) : (
            <>
              <span className={`badge decided-${change.decision}`}>{t(`proposal.${change.decision}`)}</span>
              {editable && <button className="link" onClick={() => onDecide('pending')}>{t('proposal.undo')}</button>}
            </>
          )}
        </div>
      </header>
      {change.stale && <div className="error">{t('proposal.stale')}</div>}

      {open && (
        <>
          {editable && pending && panel === 'revise' && (
            <div className="panel">
              <label>
                <span className="hint">{t('proposal.reviseHint')}</span>
                <textarea rows={3} value={reviseText} onChange={(e) => setReviseText(e.target.value)} autoFocus />
              </label>
              <div className="actions">
                <button className="primary" onClick={async () => { if (await onRevise(reviseText)) { setPanel('none'); setReviseText('') } }}>
                  {t('proposal.reviseSend')}
                </button>
                <button onClick={() => setPanel('none')}>{t('common.cancel')}</button>
              </div>
            </div>
          )}

          {editable && pending && panel === 'edit' ? (
            <div className="panel">
              <textarea className="editor" rows={Math.min(40, draft.split('\n').length + 2)} value={draft} onChange={(e) => setDraft(e.target.value)} />
              <div className="actions">
                <button className="primary" disabled={draft === change.content} onClick={async () => { if (await onEdit(draft)) setPanel('none') }}>
                  {t('proposal.editSave')}
                </button>
                <button onClick={() => setPanel('none')}>{t('common.cancel')}</button>
              </div>
            </div>
          ) : (
            <>
              <nav className="tabs">
                {(['preview', 'diff', 'source'] as const).map((k) => (
                  <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{t(`proposal.tab.${k}`)}</button>
                ))}
              </nav>
              <div className="change-body">
                {tab === 'preview' && <ArticleView content={change.content} />}
                {tab === 'diff' && <DiffView before={change.base_content ?? ''} after={change.content} />}
                {tab === 'source' && <pre className="source-md">{change.content}</pre>}
              </div>
            </>
          )}

          {change.history.length > 0 && (
            <details className="history">
              <summary>{t('proposal.history', { count: String(change.history.length) })}</summary>
              <ol reversed>
                {change.history.slice().reverse().map((h, i) => (
                  <li key={i}>
                    <details>
                      <summary>
                        {t(`proposal.history.${h.replaced_by}`)} · {h.by} · <span className="muted">{formatTime(h.at)}</span>
                        {h.note && <div className="note">“{h.note}”</div>}
                      </summary>
                      <DiffView before={h.content} after={change.content} />
                    </details>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </>
      )}
    </article>
  )
}
