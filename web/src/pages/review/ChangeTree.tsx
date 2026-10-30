import { useState } from 'react'
import type { ArticleChange } from '../../api'
import { useI18n } from '../../i18n'

type Folder = { name: string; path: string; folders: Folder[]; files: ArticleChange[] }

const KIND_LETTER = { create: 'A', update: 'M', retire: 'R' } as const

/** Group changes by folder; a folder with a single subfolder and no files is merged into it, like VS Code's compact folders. */
function buildTree(changes: ArticleChange[]): Folder {
  const root: Folder = { name: '', path: '', folders: [], files: [] }
  for (const c of changes) {
    const parts = c.path.split('/')
    parts.pop()
    let node = root
    for (const part of parts) {
      const path = node.path ? `${node.path}/${part}` : part
      let next = node.folders.find((f) => f.path === path)
      if (!next) {
        next = { name: part, path, folders: [], files: [] }
        node.folders.push(next)
      }
      node = next
    }
    node.files.push(c)
  }
  const compact = (f: Folder): Folder => {
    let node = f
    while (node.files.length === 0 && node.folders.length === 1) {
      const only = node.folders[0]
      node = { ...only, name: node.name ? `${node.name}/${only.name}` : only.name }
    }
    return { ...node, folders: node.folders.map(compact) }
  }
  return { ...root, folders: root.folders.map(compact) }
}

/** The Article changes section of the sidebar for the open Proposal. */
export function ChangeTree({ changes, selected, onSelect, collapsed, onCollapse }: {
  changes: ArticleChange[] | undefined
  selected: string | undefined
  onSelect: (id: string) => void
  collapsed: boolean
  onCollapse: (collapsed: boolean) => void
}) {
  const { t } = useI18n()
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const decided = changes?.filter((c) => c.decision !== 'pending').length ?? 0
  // Number changes in Proposal order so the count reads the same in the tree and the status bar.
  const number = new Map(changes?.map((c, i) => [c.id, i + 1]))

  const toggleFolder = (path: string) => {
    const next = new Set(closed)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setClosed(next)
  }

  const renderFolder = (folder: Folder, depth: number) => (
    <>
      {folder.folders.map((f) => (
        <li key={`d:${f.path}`}>
          <button className="tree-row tree-folder" style={{ paddingLeft: 8 + depth * 12 }} onClick={() => toggleFolder(f.path)} aria-expanded={!closed.has(f.path)}>
            <span className={`chevron${closed.has(f.path) ? '' : ' open'}`} aria-hidden="true" />
            <span className="tree-name">{f.name}</span>
          </button>
          {!closed.has(f.path) && <ul>{renderFolder(f, depth + 1)}</ul>}
        </li>
      ))}
      {folder.files.map((c) => (
        <li key={c.id}>
          <button
            className={`tree-row tree-file decision-${c.decision}${c.stale ? ' stale' : ''}${c.id === selected ? ' selected' : ''}`}
            style={{ paddingLeft: 10 + depth * 12 }}
            onClick={() => onSelect(c.id)}
            title={`${c.title}\n${c.path}`}
          >
            <span className="tree-index">{number.get(c.id)}</span>
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
      ))}
    </>
  )

  return (
    <section className={`side-section side-changes${collapsed ? ' collapsed' : ''}`}>
      <div className="side-head">
        <button className="side-title" onClick={() => onCollapse(!collapsed)} aria-expanded={!collapsed}>
          <span className="chevron" aria-hidden="true" />
          {t('review.changes')}
          {changes && changes.length > 0 && <span className="count count-strong">{changes.length}</span>}
        </button>
      </div>
      {!collapsed && changes && changes.length > 0 && (
        <div className="side-progress" title={t('proposal.decidedCount', { done: String(decided), total: String(changes.length) })}>
          <span>{t('proposal.decidedCount', { done: String(decided), total: String(changes.length) })}</span>
          <span className="progress-track"><span className="progress-fill" style={{ width: `${(decided / changes.length) * 100}%` }} /></span>
        </div>
      )}
      {!collapsed && (
        <div className="side-body">
          {changes === undefined ? (
            <p className="side-empty">{t('review.noProposalOpen')}</p>
          ) : changes.length === 0 ? (
            <p className="side-empty">{t('review.noChanges')}</p>
          ) : (
            <ul className="tree">{renderFolder(buildTree(changes), 0)}</ul>
          )}
        </div>
      )}
    </section>
  )
}

function DecisionMark({ change }: { change: ArticleChange }) {
  const { t } = useI18n()
  if (change.stale) return <span className="tree-mark mark-stale" title={t('proposal.staleShort')}>!</span>
  if (change.decision === 'accepted') return <span className="tree-mark mark-accepted" title={t('proposal.accepted')}>✓</span>
  if (change.decision === 'discarded') return <span className="tree-mark mark-discarded" title={t('proposal.discarded')}>✕</span>
  return <span className="tree-mark mark-pending" title={t('proposal.pending')}>●</span>
}
