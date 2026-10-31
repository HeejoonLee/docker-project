import { lazy, Suspense, useState } from 'react'
import type { ArticleChange, Decision } from '../../api'
import { DiffView, type DiffMode } from '../../diff'
import { useI18n } from '../../i18n'
import { ArticleView } from '../../markdown'
import { formatShortTime, formatTime } from '../../ui'
import { sendKeys } from './sendKeys'

type Tab = 'preview' | 'diff' | 'source' | 'history'

// CodeMirror is only needed once someone opens Markdown or Edit, so it loads on demand.
const CodeEditor = lazy(() => import('../../CodeEditor'))

/**
 * The editor area for one Article change: its header with the decisions, then
 * Preview / Changes / Markdown / History. Revise opens a box for the agent right
 * under the header, so the request is visibly about this Article and nothing else.
 */
export function ChangeEditor({ change, reviewable, diffMode, onDiffMode, compare, onCompare, onCloseCompare, onDecide, onRevise, onEdit, hasSource, sourceOpen, onToggleSource, cites, onOpenSource }: {
  change: ArticleChange
  reviewable: boolean
  diffMode: DiffMode
  onDiffMode: (mode: DiffMode) => void
  /** Index into change.history to diff against the current version, if any. */
  compare: number | null
  onCompare: (index: number) => void
  onCloseCompare: () => void
  onDecide: (d: Decision) => void
  onRevise: (text: string) => Promise<boolean>
  onEdit: (content: string) => Promise<boolean>
  hasSource: boolean
  sourceOpen: boolean
  onToggleSource: () => void
  /** The Proposal's Sources this Article cites, labelled as in the Source pane. */
  cites: { id: string; label: string; title: string }[]
  onOpenSource: (id: string) => void
}) {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>(change.kind === 'create' ? 'preview' : 'diff')
  const [editing, setEditing] = useState(false)
  const [revising, setRevising] = useState(false)
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
            canEdit && !editing && !revising && (
              <>
                <button className="primary" disabled={change.stale} onClick={() => onDecide('accepted')}>{t('proposal.accept')}</button>
                <button onClick={() => setRevising(true)}>{t('proposal.revise')}</button>
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
      {revising && canEdit && (
        <ReviseBox title={change.title} onRevise={onRevise} onDone={() => setRevising(false)} />
      )}

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
              {change.history.length > 0 && (
                <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>
                  {t('proposal.tab.history', { count: String(change.history.length) })}
                </button>
              )}
            </nav>
            <div className="actions">
              {tab === 'diff' && <DiffModeToggle mode={diffMode} onChange={onDiffMode} />}
              {cites.length > 0 && (
                <span className="cites">
                  {t('proposal.cites')}
                  {cites.map((c) => (
                    <button key={c.id} className="small-button" title={c.title} onClick={() => onOpenSource(c.id)}>{c.label}</button>
                  ))}
                </span>
              )}
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
            {tab === 'history' && <History change={change} onCompare={onCompare} />}
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

/** The request to the agent for a new version of this one Article change. */
function ReviseBox({ title, onRevise, onDone }: {
  title: string
  onRevise: (text: string) => Promise<boolean>
  onDone: () => void
}) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const send = async () => {
    setSending(true)
    const ok = await onRevise(text)
    setSending(false)
    if (ok) onDone()
  }
  return (
    <div className="revise-box">
      <label>
        <strong>{t('review.reviseTitle', { title })}</strong>
        <span className="hint">{t('proposal.reviseHint')}</span>
        <textarea autoFocus rows={3} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={sendKeys(send, onDone)} />
      </label>
      <div className="revise-actions">
        <span className="hint">{t('review.sendShortcut')}</span>
        <button onClick={onDone}>{t('common.cancel')}</button>
        <button className="primary" disabled={sending} onClick={send}>{t('proposal.reviseSend')}</button>
      </div>
    </div>
  )
}

/** Earlier versions of this Article change, newest first, each comparable with the current one. */
function History({ change, onCompare }: { change: ArticleChange; onCompare: (index: number) => void }) {
  const { t } = useI18n()
  return (
    <div className="history">
      <p className="muted small">{t('review.historyCompare')}</p>
      <ol className="timeline" reversed>
        <li className="timeline-current">
          <span className="timeline-what">{t('review.current')}</span>
          {change.edited_by && <span className="muted small"> · {t('proposal.editedBy', { name: change.edited_by })}</span>}
        </li>
        {change.history.map((h, i) => ({ h, i })).reverse().map(({ h, i }) => (
          <li key={i}>
            <div>
              <span className="timeline-what">{t(`proposal.history.${h.replaced_by}`)}</span>
              <span className="muted small"> · {h.by} · <span title={formatTime(h.at)}>{formatShortTime(h.at)}</span></span>
            </div>
            {h.note && <div className="note">“{h.note}”</div>}
            <button className="link small" onClick={() => onCompare(i)}>{t('review.compare')}</button>
          </li>
        ))}
      </ol>
    </div>
  )
}
