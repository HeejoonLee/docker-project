import { useState } from 'react'
import type { ArticleChange } from '../../api'
import { useI18n } from '../../i18n'
import { groupByFolder } from './order'

const KIND_LETTER = { create: 'A', update: 'M', retire: 'R' } as const

/** The open Proposal's Article changes, grouped under their parent folders like files in a tree. */
export function ChangeRows({ changes, selected, onSelect }: {
  changes: ArticleChange[]
  selected: string | undefined
  onSelect: (id: string) => void
}) {
  const { t } = useI18n()
  const [closed, setClosed] = useState<Set<string>>(new Set())
  if (changes.length === 0) return <p className="side-empty nested">{t('review.noChanges')}</p>
  const decided = changes.filter((c) => c.decision !== 'pending').length
  const progress = t('proposal.decidedCount', { done: String(decided), total: String(changes.length) })
  let n = 0

  const toggle = (dir: string) => {
    const next = new Set(closed)
    if (next.has(dir)) next.delete(dir)
    else next.add(dir)
    setClosed(next)
  }

  const fileRow = (c: ArticleChange, index: number) => (
    <li key={c.id}>
      <button
        className={`tree-row tree-file decision-${c.decision}${c.stale ? ' stale' : ''}${c.id === selected ? ' selected' : ''}`}
        onClick={() => onSelect(c.id)}
        title={`${c.title}\n${c.path}`}
      >
        <span className="tree-index">{index}</span>
        <span className="tree-text">
          <span className="tree-name">{c.title}</span>
          <span className="tree-sub">
            <span className={`tree-kind kind-letter-${c.kind}`} title={t(`proposal.kind.${c.kind}`)}>{KIND_LETTER[c.kind]}</span>
            <span className="tree-file-name">{c.path.split('/').pop()}</span>
          </span>
        </span>
        <DecisionMark change={c} />
      </button>
    </li>
  )

  return (
    <>
      <div className="side-progress" title={progress}>
        <span>{progress}</span>
        <span className="progress-track"><span className="progress-fill" style={{ width: `${(decided / changes.length) * 100}%` }} /></span>
      </div>
      {groupByFolder(changes).map((g) => {
        // Number every file even when its folder is folded, so numbers stay stable.
        const rows = g.changes.map((c) => fileRow(c, ++n))
        if (!g.dir) return <ul key="(root)" className="change-rows">{rows}</ul>
        const isOpen = !closed.has(g.dir)
        return (
          <div key={g.dir} className="change-folder">
            <button className="tree-row tree-folder" onClick={() => toggle(g.dir)} aria-expanded={isOpen} title={g.dir}>
              <span className={`chevron${isOpen ? ' open' : ''}`} aria-hidden="true" />
              <FolderIcon />
              <span className="tree-name">{g.dir}</span>
              <span className="count">{g.changes.length}</span>
            </button>
            {isOpen && <ul className="change-rows in-folder">{rows}</ul>}
          </div>
        )
      })}
    </>
  )
}

function FolderIcon() {
  return (
    <svg className="folder-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2.2h8.4A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z" />
    </svg>
  )
}

function DecisionMark({ change }: { change: ArticleChange }) {
  const { t } = useI18n()
  if (change.stale) return <span className="tree-mark mark-stale" title={t('proposal.staleShort')}>!</span>
  if (change.decision === 'accepted') return <span className="tree-mark mark-accepted" title={t('proposal.accepted')}>✓</span>
  if (change.decision === 'discarded') return <span className="tree-mark mark-discarded" title={t('proposal.discarded')}>✕</span>
  return <span className="tree-mark mark-pending" title={t('proposal.pending')}>●</span>
}
