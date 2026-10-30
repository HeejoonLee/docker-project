import type { ArticleChange } from '../../api'
import { useI18n } from '../../i18n'

const KIND_LETTER = { create: 'A', update: 'M', retire: 'R' } as const

/** The open Proposal's Article changes, listed under it like files in a folder. */
export function ChangeRows({ changes, selected, onSelect }: {
  changes: ArticleChange[]
  selected: string | undefined
  onSelect: (id: string) => void
}) {
  const { t } = useI18n()
  if (changes.length === 0) return <p className="side-empty nested">{t('review.noChanges')}</p>
  const decided = changes.filter((c) => c.decision !== 'pending').length
  const progress = t('proposal.decidedCount', { done: String(decided), total: String(changes.length) })
  return (
    <>
      <div className="side-progress" title={progress}>
        <span>{progress}</span>
        <span className="progress-track"><span className="progress-fill" style={{ width: `${(decided / changes.length) * 100}%` }} /></span>
      </div>
      <ul className="change-rows">
        {changes.map((c, i) => (
          <li key={c.id}>
            <button
              className={`tree-row tree-file decision-${c.decision}${c.stale ? ' stale' : ''}${c.id === selected ? ' selected' : ''}`}
              onClick={() => onSelect(c.id)}
              title={`${c.title}\n${c.path}`}
            >
              <span className="tree-index">{i + 1}</span>
              <span className="tree-text">
                <span className="tree-name">{c.title}</span>
                <span className="tree-sub">
                  <span className={`tree-kind kind-letter-${c.kind}`} title={t(`proposal.kind.${c.kind}`)}>{KIND_LETTER[c.kind]}</span>
                  <span className="tree-file-name">{c.path}</span>
                </span>
              </span>
              <DecisionMark change={c} />
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

function DecisionMark({ change }: { change: ArticleChange }) {
  const { t } = useI18n()
  if (change.stale) return <span className="tree-mark mark-stale" title={t('proposal.staleShort')}>!</span>
  if (change.decision === 'accepted') return <span className="tree-mark mark-accepted" title={t('proposal.accepted')}>✓</span>
  if (change.decision === 'discarded') return <span className="tree-mark mark-discarded" title={t('proposal.discarded')}>✕</span>
  return <span className="tree-mark mark-pending" title={t('proposal.pending')}>●</span>
}
