import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type ArticleChange, type Decision, type Proposal } from '../api'
import { useI18n } from '../i18n'
import { ArticleView, DiffView } from '../markdown'
import { useUser } from '../user'
import { ErrorBox, StateBadge } from '../ui'
import { usePoll } from '../usePoll'
import { useConfig } from '../config'

const BUSY = new Set(['generating', 'committing'])

export default function ProposalPage() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const { name } = useUser()
  const config = useConfig()
  const { data: p, error, setData } = usePoll(() => api.proposal(id), id, 2000, (d) => !d || BUSY.has(d.state))
  const [actionError, setActionError] = useState<unknown>()

  const act = async (fn: () => Promise<Proposal>) => {
    try {
      setActionError(undefined)
      setData(await fn())
    } catch (err) {
      setActionError(err)
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
          </p>
        </div>
        {temporalLink && <a className="small" href={temporalLink} target="_blank" rel="noreferrer">{t('proposal.openTemporal')} ↗</a>}
      </div>

      <details className="source">
        <summary>{t('proposal.source')}</summary>
        <pre>{p.text}</pre>
      </details>

      {p.state === 'generating' && <p className="notice">{t('proposal.generating')}</p>}
      {p.state === 'committing' && <p className="notice">{t('proposal.committing')}</p>}
      {p.state === 'done' && <p className="notice ok">{t('proposal.committed', { commit: (p.commit ?? '').slice(0, 8), name: p.reviewer ?? '' })}</p>}
      {p.state === 'discarded' && <p className="notice">{t('proposal.discardedAll', { name: p.reviewer ?? '' })}</p>}
      {p.error && <div className="error">{p.error}</div>}
      <ErrorBox error={actionError} />

      {p.changes.map((c) => (
        <ChangeCard
          key={c.id}
          change={c}
          editable={reviewable}
          onDecide={(d) => act(() => api.decide(p.id, c.id, d))}
        />
      ))}

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

function ChangeCard({ change, editable, onDecide }: { change: ArticleChange; editable: boolean; onDecide: (d: Decision) => void }) {
  const { t } = useI18n()
  const [tab, setTab] = useState<'preview' | 'diff' | 'source'>(change.kind === 'create' ? 'preview' : 'diff')
  return (
    <article className={`change decision-${change.decision}${change.stale ? ' stale' : ''}`}>
      <header>
        <div>
          <span className={`kind kind-${change.kind}`}>{t(`proposal.kind.${change.kind}`)}</span>
          <strong>{change.title}</strong>
          <code className="path">{change.path}</code>
        </div>
        <div className="decide">
          {change.decision === 'pending' ? (
            editable && (
              <>
                <button className="primary" disabled={change.stale} onClick={() => onDecide('accepted')}>{t('proposal.accept')}</button>
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
    </article>
  )
}
