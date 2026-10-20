import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox, StateBadge, formatTime } from '../ui'
import { usePoll } from '../usePoll'

const STATES = ['generating', 'awaiting_review', 'committing', 'done', 'discarded', 'failed']

export default function Inbox() {
  const { t } = useI18n()
  const [params, setParams] = useSearchParams()
  const bundle = params.get('bundle') ?? ''
  const state = params.get('state') ?? ''
  const bundles = usePoll(api.bundles, 'bundles', 30000)
  const proposals = usePoll(() => api.proposals({ bundle, state }), `${bundle}|${state}`, 4000)

  const setFilter = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next)
  }

  return (
    <section>
      <div className="page-head">
        <h1>{t('inbox.title')}</h1>
        <div className="filters">
          <label>
            {t('inbox.bundle')}
            <select value={bundle} onChange={(e) => setFilter('bundle', e.target.value)}>
              <option value="">{t('common.all')}</option>
              {bundles.data?.map((b) => <option key={b.slug} value={b.slug}>{b.name}</option>)}
            </select>
          </label>
          <label>
            {t('inbox.state')}
            <select value={state} onChange={(e) => setFilter('state', e.target.value)}>
              <option value="">{t('common.all')}</option>
              {STATES.map((s) => <option key={s} value={s}>{t(`state.${s}`)}</option>)}
            </select>
          </label>
        </div>
      </div>
      <ErrorBox error={proposals.error} />
      {proposals.data === undefined ? (
        <p className="muted">{t('common.loading')}</p>
      ) : proposals.data.length === 0 ? (
        <p className="muted">{t('inbox.empty')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('inbox.col.title')}</th>
                <th>{t('inbox.col.bundle')}</th>
                <th>{t('inbox.col.by')}</th>
                <th>{t('inbox.col.state')}</th>
                <th>{t('inbox.col.created')}</th>
              </tr>
            </thead>
            <tbody>
              {proposals.data.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/proposals/${p.id}`}>{p.title}</Link></td>
                  <td>{p.bundle}</td>
                  <td>{p.submitted_by}</td>
                  <td><StateBadge state={p.state} /></td>
                  <td className="muted nowrap">{formatTime(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
