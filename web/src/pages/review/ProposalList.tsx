import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import type { BundleSummary, ProposalSummary } from '../../api'
import { useI18n } from '../../i18n'
import { ErrorBox, formatShortTime } from '../../ui'

const STATES = ['generating', 'awaiting_review', 'committing', 'done', 'discarded', 'failed']

export type ProposalFilter = { bundle: string; state: string }

/** The Proposals section of the sidebar: a filterable queue, newest first. */
export function ProposalList({ proposals, error, bundles, filter, onFilter, collapsed, onCollapse }: {
  proposals: ProposalSummary[] | undefined
  error: unknown
  bundles: BundleSummary[] | undefined
  filter: ProposalFilter
  onFilter: (f: ProposalFilter) => void
  collapsed: boolean
  onCollapse: (collapsed: boolean) => void
}) {
  const { t } = useI18n()
  const filtered = filter.bundle !== '' || filter.state !== ''
  const [showFilters, setShowFilters] = useState(false)

  return (
    <section className={`side-section${collapsed ? ' collapsed' : ''}`}>
      <div className="side-head">
        <button className="side-title" onClick={() => onCollapse(!collapsed)} aria-expanded={!collapsed}>
          <span className="chevron" aria-hidden="true" />
          {t('review.proposals')}
          {proposals && <span className="count">{proposals.length}</span>}
        </button>
        <button
          className={`icon-button${showFilters || filtered ? ' active' : ''}`}
          title={t('review.filter')}
          aria-pressed={showFilters}
          onClick={() => { setShowFilters(!showFilters); onCollapse(false) }}
        >
          <FilterIcon />
        </button>
        <Link className="icon-button" to="/new" title={t('review.newProposal')}>+</Link>
      </div>
      {!collapsed && (
        <>
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
            {proposals === undefined ? (
              <p className="side-empty">{t('common.loading')}</p>
            ) : proposals.length === 0 ? (
              <p className="side-empty">{t('review.emptyQueue')}</p>
            ) : (
              <ul className="proposal-list">
                {proposals.map((p) => (
                  <li key={p.id}>
                    <NavLink to={`/proposals/${p.id}`} className="proposal-row" title={p.title}>
                      <span className={`state-dot state-${p.state}`} title={t(`state.${p.state}`)} />
                      <span className="proposal-row-text">
                        <span className="proposal-row-title">{p.title}</span>
                        <span className="proposal-row-meta">{p.bundle} · {p.submitted_by} · {formatShortTime(p.created_at)}</span>
                      </span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
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
