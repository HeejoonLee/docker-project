import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type ArticleChange, type Decision, type Proposal } from '../api'
import { useConfig } from '../config'
import { useI18n } from '../i18n'
import { ArticleView, DiffView } from '../markdown'
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
          <pre>{p.summary}</pre>
        </details>
      )}

      {reviewable && p.changes.length === 0 && <p className="notice">{t('proposal.noChanges')}</p>}

      {p.changes.map((c) => (
        <ChangeCard
          key={c.id}
          change={c}
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
          <span className="muted">{t('proposal.submitHint')}</span>
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

type Panel = 'none' | 'revise' | 'edit'

function ChangeCard({ change, editable, onDecide, onRevise, onEdit }: {
  change: ArticleChange
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
    <article className={`change decision-${change.decision}${change.stale ? ' stale' : ''}`}>
      <header>
        <div>
          <span className={`kind kind-${change.kind}`}>{t(`proposal.kind.${change.kind}`)}</span>
          <strong>{change.title}</strong>
          <code className="path">{change.path}</code>
          {change.edited_by && <span className="muted small">{t('proposal.editedBy', { name: change.edited_by })}</span>}
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
    </article>
  )
}
