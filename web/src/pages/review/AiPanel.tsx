import { useState, type RefObject } from 'react'
import type { ArticleChange, Proposal } from '../../api'
import { useI18n } from '../../i18n'
import { Markdown } from '../../markdown'
import { formatShortTime, formatTime } from '../../ui'

/**
 * Everything addressed to the agent. The Proposal section reaches every undecided
 * Article change; the Article change section reaches only the selected one.
 */
export function AiPanel({ p, change, reviewable, compare, onCompare, onFeedback, onRevise, reviseRef, onClose }: {
  p: Proposal
  change: ArticleChange | undefined
  reviewable: boolean
  compare: number | null
  onCompare: (index: number) => void
  onFeedback: (text: string) => Promise<boolean>
  onRevise: (text: string) => Promise<boolean>
  reviseRef: RefObject<HTMLTextAreaElement | null>
  onClose: () => void
}) {
  const { t } = useI18n()
  const [feedback, setFeedback] = useState('')
  const canRevise = reviewable && change?.decision === 'pending'

  return (
    <aside className="ai-panel">
      <div className="pane-head">
        <span>{t('review.ai')}</span>
        <button className="icon-button" onClick={onClose} title={t('review.aiClose')}>»</button>
      </div>
      <div className="ai-scroll">
        <section className="ai-section">
          <h3>{t('review.proposalSection')}</h3>
          {p.summary ? (
            <details className="ai-summary" open>
              <summary>{t('proposal.summary')}</summary>
              <Markdown text={p.summary} />
            </details>
          ) : (
            <p className="muted small">{t('review.noSummary')}</p>
          )}
          {reviewable && (
            <div className="ai-compose">
              <label>
                <strong>{t('proposal.feedbackTitle')}</strong>
                <span className="hint">{t('proposal.feedbackHint')}</span>
                <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
              </label>
              <button disabled={!feedback.trim()} onClick={async () => { if (await onFeedback(feedback)) setFeedback('') }}>
                {t('proposal.feedbackSend')}
              </button>
            </div>
          )}
        </section>

        {change && (
          <section className="ai-section">
            <h3>{t('review.changeSection')}</h3>
            <p className="ai-change-title" title={change.path}>{change.title}</p>
            <ol className="timeline" reversed>
              <li className="timeline-current">
                <span className="timeline-what">{t('review.current')}</span>
                {change.edited_by && <span className="muted small"> · {t('proposal.editedBy', { name: change.edited_by })}</span>}
              </li>
              {change.history.map((h, i) => ({ h, i })).reverse().map(({ h, i }) => (
                <li key={i} className={compare === i ? 'active' : ''}>
                  <div>
                    <span className="timeline-what">{t(`proposal.history.${h.replaced_by}`)}</span>
                    <span className="muted small"> · {h.by} · <span title={formatTime(h.at)}>{formatShortTime(h.at)}</span></span>
                  </div>
                  {h.note && <div className="note">“{h.note}”</div>}
                  <button className="link small" onClick={() => onCompare(i)}>{t('review.compare')}</button>
                </li>
              ))}
            </ol>
            {canRevise ? (
              <ReviseBox key={change.id} onRevise={onRevise} reviseRef={reviseRef} />
            ) : reviewable && (
              <p className="muted small">{t('review.reviseDecided')}</p>
            )}
          </section>
        )}
      </div>
    </aside>
  )
}

function ReviseBox({ onRevise, reviseRef }: {
  onRevise: (text: string) => Promise<boolean>
  reviseRef: RefObject<HTMLTextAreaElement | null>
}) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  return (
    <div className="ai-compose">
      <label>
        <strong>{t('proposal.revise')}</strong>
        <span className="hint">{t('proposal.reviseHint')}</span>
        <textarea ref={reviseRef} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <button onClick={async () => { if (await onRevise(text)) setText('') }}>{t('proposal.reviseSend')}</button>
    </div>
  )
}
