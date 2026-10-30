import { useEffect, useRef, useState } from 'react'
import { Link, useMatch, useSearchParams } from 'react-router-dom'
import type { DiffMode } from '../../diff'
import { api, type ArticleChange, type Decision, type Proposal } from '../../api'
import { useI18n } from '../../i18n'
import { ErrorBox } from '../../ui'
import { usePoll } from '../../usePoll'
import { useUser } from '../../user'
import { AiPanel } from './AiPanel'
import { ChangeEditor } from './ChangeEditor'
import { ChangeTree } from './ChangeTree'
import { Splitter, useStored } from './layout'
import { ProposalList, type ProposalFilter } from './ProposalList'
import { SourcePane } from './SourcePane'
import './review.css'

const BUSY = new Set(['generating', 'committing'])

/**
 * The review workspace behind /inbox and /proposals/:id, laid out like an IDE:
 * Proposals and Article changes on the left, the selected Article change in the
 * middle, the agent on the right, and the review status along the bottom.
 */
export default function ReviewWorkspace() {
  const { t } = useI18n()
  const { name } = useUser()
  const id = useMatch('/proposals/:id')?.params.id
  const [params, setParams] = useSearchParams()

  const [filter, setFilter] = useStored<ProposalFilter>('review.filter', { bundle: '', state: 'awaiting_review' })
  const bundles = usePoll(api.bundles, 'bundles', 30000)
  const list = usePoll(() => api.proposals(filter), `${filter.bundle}|${filter.state}`, 4000)
  const proposal = usePoll<Proposal | undefined>(
    () => (id ? api.proposal(id) : Promise.resolve(undefined)),
    id ?? '',
    5000,
    (d) => !!id && (!d || BUSY.has(d.state) || (d.state === 'awaiting_review' && d.reference_used)),
  )
  // Ignore a response that arrives for a Proposal we've already navigated away from.
  const p = proposal.data?.id === id ? proposal.data : undefined

  const [sidebarWidth, setSidebarWidth] = useStored('review.sidebarWidth', 280)
  const [sidebarHidden, setSidebarHidden] = useStored('review.sidebarHidden', false)
  const [listHeight, setListHeight] = useStored('review.listHeight', 300)
  const [listCollapsed, setListCollapsed] = useStored('review.listCollapsed', false)
  const [treeCollapsed, setTreeCollapsed] = useStored('review.treeCollapsed', false)
  const [aiWidth, setAiWidth] = useStored('review.aiWidth', 360)
  const [aiOpen, setAiOpen] = useState(() => window.innerWidth >= 1600)
  const [sourceOpen, setSourceOpen] = useStored('review.sourceOpen', false)
  const [sourceWidth, setSourceWidth] = useStored('review.sourceWidth', 480)
  const [diffMode, setDiffMode] = useStored<DiffMode>('review.diffMode', 'split')
  const [compare, setCompare] = useState<{ change: string; index: number } | null>(null)
  // Errors are tagged with their Proposal so they disappear when another one is opened.
  const [failure, setFailure] = useState<{ id: string | undefined; error: unknown }>()
  const actionError = failure?.id === id ? failure?.error : undefined
  const reviseRef = useRef<HTMLTextAreaElement>(null)
  const [focusRevise, setFocusRevise] = useState(0)

  useEffect(() => { if (focusRevise) reviseRef.current?.focus() }, [focusRevise])

  const changeParam = params.get('change')
  const current = p && (p.changes.find((c) => c.id === changeParam) ?? p.changes.find((c) => c.decision === 'pending') ?? p.changes[0])
  const reviewable = p?.state === 'awaiting_review'

  const select = (cid: string) => {
    setCompare(null)
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('change', cid)
      return next
    }, { replace: true })
  }

  const act = async (fn: () => Promise<Proposal>) => {
    try {
      setFailure(undefined)
      const next = await fn()
      proposal.setData(next)
      list.reload()
      return next
    } catch (err) {
      setFailure({ id, error: err })
      return undefined
    }
  }

  // After a decision, move on to the next undecided Article change.
  const decide = async (c: ArticleChange, d: Decision) => {
    if (!p) return
    const next = await act(() => api.decide(p.id, c.id, d))
    if (!next || d === 'pending') return
    const i = next.changes.findIndex((x) => x.id === c.id)
    const upcoming = [...next.changes.slice(i + 1), ...next.changes.slice(0, i)].find((x) => x.decision === 'pending')
    if (upcoming) select(upcoming.id)
  }

  const openRevise = () => {
    setAiOpen(true)
    setFocusRevise((n) => n + 1)
  }

  const bothSections = !listCollapsed && !treeCollapsed

  return (
    <div className="workspace">
      <div className="workspace-panes">
        {sidebarHidden ? (
          <div className="side-strip">
            <button className="icon-button" onClick={() => setSidebarHidden(false)} title={t('review.showSidebar')}>»</button>
          </div>
        ) : (
          <>
            <aside className="sidebar" style={{ width: sidebarWidth }}>
              <div className="pane-head">
                <span>{t('inbox.title')}</span>
                <button className="icon-button" onClick={() => setSidebarHidden(true)} title={t('review.hideSidebar')}>«</button>
              </div>
              <div className="sidebar-sections">
                <div className={`sidebar-list${bothSections ? ' fit' : ''}`} style={bothSections ? { maxHeight: listHeight } : listCollapsed ? undefined : { flex: 1 }}>
                  <ProposalList
                    proposals={list.data}
                    error={list.error}
                    bundles={bundles.data}
                    filter={filter}
                    onFilter={setFilter}
                    collapsed={listCollapsed}
                    onCollapse={setListCollapsed}
                  />
                </div>
                {bothSections && <Splitter axis="y" value={listHeight} onChange={setListHeight} min={90} max={900} />}
                <div className="sidebar-tree" style={treeCollapsed ? undefined : { flex: 1 }}>
                  <ChangeTree
                    changes={p?.changes}
                    selected={current?.id}
                    onSelect={select}
                    collapsed={treeCollapsed}
                    onCollapse={setTreeCollapsed}
                  />
                </div>
              </div>
            </aside>
            <Splitter axis="x" value={sidebarWidth} onChange={setSidebarWidth} min={200} max={640} />
          </>
        )}

        <div className="editor-area">
          {!id ? (
            <div className="editor-empty">
              <p>{t('review.pick')}</p>
              {list.data && <p className="muted">{t('review.queueCount', { count: String(list.data.length) })}</p>}
              <Link className="button" to="/new">{t('review.newProposal')}</Link>
            </div>
          ) : !p ? (
            <div className="editor-empty">{proposal.error ? <ErrorBox error={proposal.error} /> : <p className="muted">{t('common.loading')}</p>}</div>
          ) : (
            <>
              <div className="breadcrumbs">
                <span className="crumb-proposal" title={p.title}>{p.title}</span>
                {current && <><span className="crumb-sep">›</span><span className="crumb-path">{current.path}</span></>}
              </div>
              <Banners p={p} reviewable={reviewable} onRefresh={() => act(() => api.refreshCode(p.id, name))} />
              <ErrorBox error={actionError} />
              <div className="editor-split">
                <div className="editor-main">
                  {current ? (
                    <ChangeEditor
                      key={current.id}
                      change={current}
                      reviewable={reviewable}
                      diffMode={diffMode}
                      onDiffMode={setDiffMode}
                      compare={compare?.change === current.id ? compare.index : null}
                      onCloseCompare={() => setCompare(null)}
                      onDecide={(d) => decide(current, d)}
                      onRevise={openRevise}
                      onEdit={async (content) => !!(await act(() => api.edit(p.id, current.id, content, name)))}
                      hasSource={!!p.source}
                      sourceOpen={sourceOpen}
                      onToggleSource={() => setSourceOpen(!sourceOpen)}
                    />
                  ) : (
                    <div className="editor-empty">
                      <p className="muted">{reviewable ? t('proposal.noChanges') : t('review.noChanges')}</p>
                    </div>
                  )}
                </div>
                {sourceOpen && p.source && (
                  <>
                    <Splitter axis="x" value={sourceWidth} onChange={setSourceWidth} min={260} max={1200} invert />
                    <div className="source-wrap" style={{ width: sourceWidth }}>
                      <SourcePane p={p} onClose={() => setSourceOpen(false)} />
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>

        {p && (aiOpen ? (
          <>
            <Splitter axis="x" value={aiWidth} onChange={setAiWidth} min={280} max={760} invert />
            <div className="ai-wrap" style={{ width: aiWidth }}>
              <AiPanel
                p={p}
                change={current}
                reviewable={reviewable}
                compare={compare && compare.change === current?.id ? compare.index : null}
                onCompare={(index) => current && setCompare({ change: current.id, index })}
                onFeedback={async (text) => !!(await act(() => api.feedback(p.id, text, name)))}
                onRevise={async (text) => !!current && !!(await act(() => api.revise(p.id, current.id, text, name)))}
                reviseRef={reviseRef}
                onClose={() => setAiOpen(false)}
              />
            </div>
          </>
        ) : (
          <div className="side-strip side-strip-right">
            <button className="ai-strip-button" onClick={() => setAiOpen(true)} title={t('review.aiOpen')}>{t('review.ai')}</button>
          </div>
        ))}
      </div>

      <StatusBar p={p} queued={list.data?.length} onSubmit={() => p && act(() => api.submit(p.id, name))} />
    </div>
  )
}

function Banners({ p, reviewable, onRefresh }: { p: Proposal; reviewable: boolean; onRefresh: () => void }) {
  const { t } = useI18n()
  return (
    <>
      {p.state === 'generating' && <div className="editor-banner working">{t('proposal.generating')}</div>}
      {p.state === 'committing' && <div className="editor-banner working">{t('proposal.committing')}</div>}
      {p.state === 'done' && <div className="editor-banner ok">{t('proposal.committed', { commit: (p.commit ?? '').slice(0, 8), name: p.reviewer ?? '' })}</div>}
      {p.state === 'discarded' && <div className="editor-banner">{t('proposal.discardedAll', { name: p.reviewer ?? '' })}</div>}
      {p.error && <div className="editor-banner bad">{p.error}</div>}
      {reviewable && p.code_stale_paths.length > 0 && (
        <div className="editor-banner bad">
          <span>
            <strong>{t('proposal.codeStale')}</strong>{' '}
            {p.code_stale_paths.map((path) => <code key={path} className="path">{path} </code>)}
          </span>
          <button onClick={onRefresh}>{t('proposal.refreshCode')}</button>
        </div>
      )}
    </>
  )
}

function StatusBar({ p, queued, onSubmit }: { p: Proposal | undefined; queued: number | undefined; onSubmit: () => void }) {
  const { t } = useI18n()
  if (!p) {
    return (
      <footer className="statusbar">
        {queued !== undefined && <span className="status-item">{t('review.queueCount', { count: String(queued) })}</span>}
      </footer>
    )
  }
  const decided = p.changes.filter((c) => c.decision !== 'pending').length
  const allDecided = decided === p.changes.length
  const reviewable = p.state === 'awaiting_review'
  return (
    <footer className="statusbar">
      <span className="status-item"><span className={`state-dot state-${p.state}`} />{t(`state.${p.state}`)}</span>
      <span className="status-item">{p.bundle}</span>
      <span className="status-item">{t('proposal.by', { name: p.submitted_by })}</span>
      {p.runs > 0 && <span className="status-item">{t('proposal.cost', { runs: String(p.runs), cost: p.cost_usd.toFixed(2) })}</span>}
      {reviewable && (
        <>
          <span className="status-hint" title={t('proposal.submitHint')}>{t('proposal.submitHint')}</span>
          <span className="status-item status-strong">
            {t('proposal.decidedCount', { done: String(decided), total: String(p.changes.length) })}
          </span>
          <button className="status-submit" disabled={!allDecided} onClick={onSubmit}>{t('proposal.submit')}</button>
        </>
      )}
    </footer>
  )
}
