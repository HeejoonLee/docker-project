import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import type { BundleSummary, Proposal, ProposalSummary } from '../../api'
import { useI18n } from '../../i18n'
import { ErrorBox, formatShortTime } from '../../ui'
import { ChangeRows } from './ChangeRows'

const STATES = ['generating', 'awaiting_review', 'committing', 'done', 'discarded', 'failed']

export type ProposalFilter = { bundle: string; state: string }

/**
 * The sidebar tree: a filterable queue of Proposals, newest first. The open Proposal
 * expands like a folder to list its Article changes underneath it.
 */
export function ProposalList({ proposals, error, bundles, filter, onFilter, open, selectedChange, onSelectChange }: {
  proposals: ProposalSummary[] | undefined
  error: unknown
  bundles: BundleSummary[] | undefined
  filter: ProposalFilter
  onFilter: (f: ProposalFilter) => void
  open: Proposal | undefined
  selectedChange: string | undefined
  onSelectChange: (id: string) => void
}) {
  const { t } = useI18n()
  const filtered = filter.bundle !== '' || filter.state !== ''
  const [showFilters, setShowFilters] = useState(false)
  const [folded, setFolded] = useState<string | null>(null)

  // A Proposal opened from elsewhere may not match the filter; keep it in the tree anyway.
  const rows = proposals && open && !proposals.some((p) => p.id === open.id)
    ? [{ id: open.id, bundle: open.bundle, title: open.title, submitted_by: open.submitted_by, state: open.state, created_at: null }, ...proposals]
    : proposals

  return (
    <section className="side-section">
      <div className="side-head">
        <span className="side-title">
          {t('review.proposals')}
          {proposals && <span className="count">{proposals.length}</span>}
        </span>
        <button
          className={`icon-button${showFilters || filtered ? ' active' : ''}`}
          title={t('review.filter')}
          aria-pressed={showFilters}
          onClick={() => setShowFilters(!showFilters)}
        >
          <FilterIcon />
        </button>
        <Link className="icon-button" to="/new" title={t('review.newProposal')}>+</Link>
      </div>
      {showFilters && (
        <div className="side-filters">
          <select aria-label={t('inbox.bundle')} value={filter.bundle} onChange={(e) => onFilter({ ...filter, bundle: e.target.value })}>
            <option value="">{t('review.allBundles')}</option>
            {bundles?.map((b) => <option key={b.slug} value={b.slug}>{b.name}</option>)}
          </select>
          <select aria-label={t('inbox.state')} value={filter.state} onChange={(e) => onFilter({ ...filter, state: e.target.value })}>
            <option value="">{t('review.allStates')}</option>
            {STATES.map((s) => <option key={s} value={s}>{t(`state.${s}`)}</option>)}
          </select>
        </div>
      )}
      <div className="side-body">
        <ErrorBox error={error} />
        {rows === undefined ? (
          <p className="side-empty">{t('common.loading')}</p>
        ) : rows.length === 0 ? (
          <p className="side-empty">{t('review.emptyQueue')}</p>
        ) : (
          <ul className="proposal-list">
            {rows.map((p) => {
              const isOpen = open?.id === p.id
              const expanded = isOpen && folded !== p.id
              return (
                <li key={p.id} className={expanded ? 'expanded' : ''}>
                  <NavLink
                    to={`/proposals/${p.id}`}
                    className="proposal-row"
                    title={p.title}
                    aria-expanded={isOpen ? expanded : false}
                    onClick={(e) => {
                      // Clicking the open Proposal folds or unfolds it instead of reloading it.
                      if (!isOpen) { setFolded(null); return }
                      e.preventDefault()
                      setFolded(expanded ? p.id : null)
                    }}
                  >
                    <span className={`chevron${expanded ? ' open' : ''}`} aria-hidden="true" />
                    <span className={`state-dot state-${p.state}`} title={t(`state.${p.state}`)} />
                    <span className="proposal-row-text">
                      <span className="proposal-row-title">{p.title}</span>
                      <span className="proposal-row-meta">{p.bundle} · {p.submitted_by}{p.created_at ? ` · ${formatShortTime(p.created_at)}` : ''}</span>
                    </span>
                    {isOpen && open.changes.length > 0 && <span className="count count-strong">{open.changes.length}</span>}
                  </NavLink>
                  {expanded && (
                    <div className="proposal-children">
                      <ChangeRows changes={open.changes} selected={selectedChange} onSelect={onSelectChange} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}

function FilterIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 5h18l-7 8v6l-4 2v-8z" />
    </svg>
  )
}
