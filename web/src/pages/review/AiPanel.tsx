import { useState } from 'react'
import type { Proposal } from '../../api'
import { useI18n } from '../../i18n'
import { Markdown } from '../../markdown'
import { sendKeys } from './sendKeys'

/**
 * The agent's side of the whole Proposal: its notes and Proposal feedback.
 * Anything about one Article change (Revise, its history) lives with that change in the editor.
 */
export function AiPanel({ p, reviewable, onFeedback, onClose }: {
  p: Proposal
  reviewable: boolean
  onFeedback: (text: string) => Promise<boolean>
  onClose: () => void
}) {
  const { t } = useI18n()
  const [feedback, setFeedback] = useState('')
  const undecided = p.changes.filter((c) => c.decision === 'pending').length
  const send = async () => {
    if (feedback.trim() && await onFeedback(feedback)) setFeedback('')
  }

  return (
    <aside className="ai-panel">
      <div className="pane-head">
        <span>{t('review.ai')}</span>
        <button className="icon-button" onClick={onClose} title={t('review.aiClose')}>»</button>
      </div>
      <div className="ai-scroll">
        <p className="ai-scope">{t('review.aiScope')}</p>
        <section className="ai-section">
          {p.summary ? (
            <details className="ai-summary" open>
              <summary>{t('proposal.summary')}</summary>
              <Markdown text={p.summary} />
            </details>
          ) : (
            <p className="muted small">{t('review.noSummary')}</p>
          )}
        </section>
        {reviewable && (
          <section className="ai-section">
            <div className="ai-compose">
              <label>
                <strong>{t('proposal.feedbackTitle')}</strong>
                <span className="hint">
                  {undecided > 0 ? t('review.feedbackReach', { count: String(undecided) }) : t('review.feedbackNothing')}
                  {' '}{t('proposal.feedbackHint')}
                </span>
                <textarea rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} onKeyDown={sendKeys(send)} />
              </label>
              <button disabled={!feedback.trim()} onClick={send}>{t('proposal.feedbackSend')}</button>
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}
