import { lazy, Suspense, useState } from 'react'
import type { ArticleChange, Decision } from '../../api'
import { DiffView, type DiffMode } from '../../diff'
import { useI18n } from '../../i18n'
import { ArticleView } from '../../markdown'
import { formatTime } from '../../ui'

type Tab = 'preview' | 'diff' | 'source'

// CodeMirror is only needed once someone opens Markdown or Edit, so it loads on demand.
const CodeEditor = lazy(() => import('../../CodeEditor'))

/** The editor area for one Article change: its header with the decisions, then Preview / Changes / Markdown. */
export function ChangeEditor({ change, reviewable, diffMode, onDiffMode, compare, onCloseCompare, onDecide, onRevise, onEdit, hasSource, sourceOpen, onToggleSource }: {
  change: ArticleChange
  reviewable: boolean
  diffMode: DiffMode
  onDiffMode: (mode: DiffMode) => void
  /** Index into change.history to diff against the current version, if any. */
  compare: number | null
  onCloseCompare: () => void
  onDecide: (d: Decision) => void
  onRevise: () => void
  onEdit: (content: string) => Promise<boolean>
  hasSource: boolean
  sourceOpen: boolean
  onToggleSource: () => void
}) {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>(change.kind === 'create' ? 'preview' : 'diff')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(change.content)
  const pending = change.decision === 'pending'
  const canEdit = reviewable && pending
  const earlier = compare !== null ? change.history[compare] : undefined

  const startEdit = () => {
    setDraft(change.content)
    setEditing(true)
  }

  return (
    <div className={`change-editor decision-${change.decision}${change.stale ? ' stale' : ''}`}>
      <header className="editor-head">
        <span className={`kind kind-${change.kind}`}>{t(`proposal.kind.${change.kind}`)}</span>
        <div className="editor-head-name">
          <strong>{change.title}</strong>
          <code className="path">{change.path}</code>
          {change.edited_by && <span className="muted small">{t('proposal.editedBy', { name: change.edited_by })}</span>}
        </div>
        <div className="decide">
          {pending ? (
            canEdit && !editing && (
              <>
                <button className="primary" disabled={change.stale} onClick={() => onDecide('accepted')}>{t('proposal.accept')}</button>
                <button onClick={onRevise}>{t('proposal.revise')}</button>
                <button onClick={startEdit}>{t('proposal.edit')}</button>
                <button className="danger" onClick={() => onDecide('discarded')}>{t('proposal.discard')}</button>
              </>
            )
          ) : (
            <>
              <span className={`badge decided-${change.decision}`}>{t(`proposal.${change.decision}`)}</span>
              {reviewable && <button className="link" onClick={() => onDecide('pending')}>{t('proposal.undo')}</button>}
            </>
          )}
        </div>
      </header>
      {change.stale && <div className="editor-banner bad">{t('proposal.stale')}</div>}

      {editing && canEdit ? (
        <>
          <div className="editor-toolbar">
            <span className="pane-toolbar-title">{t('review.editing', { path: change.path })}</span>
            <div className="actions">
              <button onClick={() => setEditing(false)}>{t('common.cancel')}</button>
              <button className="primary" disabled={draft === change.content} onClick={async () => { if (await onEdit(draft)) setEditing(false) }}>
                {t('proposal.editSave')}
              </button>
            </div>
          </div>
          <div className="editor-body code">
            <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
              <CodeEditor value={draft} onChange={setDraft} />
            </Suspense>
          </div>
        </>
      ) : earlier ? (
        <>
          <div className="editor-toolbar">
            <span className="pane-toolbar-title">
              {t('review.comparing', { what: t(`proposal.history.${earlier.replaced_by}`), when: formatTime(earlier.at) })}
            </span>
            <div className="actions">
              <DiffModeToggle mode={diffMode} onChange={onDiffMode} />
              <button onClick={onCloseCompare}>{t('review.closeCompare')}</button>
            </div>
          </div>
          <div className="editor-body">
            <DiffView key={diffMode} before={earlier.content} after={change.content} mode={diffMode} />
          </div>
        </>
      ) : (
        <>
          <div className="editor-toolbar">
            <nav className="tabs">
              {(['preview', 'diff', 'source'] as const).map((k) => (
                <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{t(`proposal.tab.${k}`)}</button>
              ))}
            </nav>
            <div className="actions">
              {tab === 'diff' && <DiffModeToggle mode={diffMode} onChange={onDiffMode} />}
              {hasSource && (
                <button className={`toggle${sourceOpen ? ' active' : ''}`} aria-pressed={sourceOpen} onClick={onToggleSource}>
                  {sourceOpen ? t('review.hideSource') : t('review.sourceBeside')}
                </button>
              )}
            </div>
          </div>
          <div className={`editor-body${tab === 'source' ? ' code' : ''}`}>
            {tab === 'preview' && <ArticleView content={change.content} />}
            {tab === 'diff' && <DiffView key={diffMode} before={change.base_content ?? ''} after={change.content} mode={diffMode} />}
            {tab === 'source' && (
              <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
                <CodeEditor value={change.content} />
              </Suspense>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function DiffModeToggle({ mode, onChange }: { mode: DiffMode; onChange: (mode: DiffMode) => void }) {
  const { t } = useI18n()
  return (
    <div className="segmented compact" role="group" aria-label={t('review.diffMode')}>
      {(['split', 'unified'] as const).map((m) => (
        <button key={m} className={mode === m ? 'active' : ''} aria-pressed={mode === m} onClick={() => onChange(m)}>
          {t(`review.diff.${m}`)}
        </button>
      ))}
    </div>
  )
}
