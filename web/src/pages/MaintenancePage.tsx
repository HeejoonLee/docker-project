import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, type BundleSummary, type Check, type MaintenanceReport, type ReportSummary, type ScheduleConfig } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox, formatTime } from '../ui'
import { usePoll } from '../usePoll'
import { useUser } from '../user'

const CHECKS: Check[] = ['integrity', 'links']

export default function MaintenancePage() {
  const { t } = useI18n()
  const { name } = useUser()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [bundles, setBundles] = useState<BundleSummary[]>()
  const slug = params.get('bundle') || bundles?.[0]?.slug || ''
  const overview = usePoll(() => (slug ? api.maintenance(slug) : Promise.resolve(undefined)), slug, 5000)
  const [error, setError] = useState<unknown>()
  const [focus, setFocus] = useState('')

  useEffect(() => { api.bundles().then(setBundles, setError) }, [])

  const run = async (check: Check) => {
    try { await api.runCheck(slug, check, name); overview.reload() } catch (err) { setError(err) }
  }
  const audit = async () => {
    try { const p = await api.audit(slug, name, focus); navigate(`/proposals/${p.id}`) } catch (err) { setError(err) }
  }

  return (
    <section>
      <div className="page-head">
        <h1>{t('mt.title')}</h1>
        {bundles && bundles.length > 0 && (
          <label className="filters">
            {t('mt.bundle')}
            <select value={slug} onChange={(e) => setParams({ bundle: e.target.value })}>
              {bundles.map((b) => <option key={b.slug} value={b.slug}>{b.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {bundles?.length === 0 && <p><Link to="/bundles">{t('new.noBundles')}</Link></p>}
      <ErrorBox error={error ?? overview.error} />
      {overview.data && (
        <>
          <p className="muted small">{t('mt.timezone', { tz: overview.data.timezone })}</p>
          <div className="check-grid">
            {CHECKS.map((check) => (
              <ScheduleCard key={`${slug}-${check}`} slug={slug} check={check} initial={overview.data!.schedules[check]} onRun={() => run(check)} />
            ))}
            <div className="card check-card">
              <h2>{t('mt.audit')}</h2>
              <p className="muted small">{t('mt.auditHint')}</p>
              <label>
                {t('mt.auditFocus')}
                <input value={focus} onChange={(e) => setFocus(e.target.value)} />
              </label>
              <div className="actions"><button className="primary" onClick={audit}>{t('mt.auditStart')}</button></div>
            </div>
          </div>

          <h2>{t('mt.reports')}</h2>
          {overview.data.reports.length === 0 ? (
            <p className="muted">{t('mt.noReports')}</p>
          ) : (
            overview.data.reports.map((r) => <ReportRow key={r.run_id} r={r} />)
          )}
        </>
      )}
    </section>
  )
}

function ScheduleCard({ slug, check, initial, onRun }: { slug: string; check: Check; initial: ScheduleConfig; onRun: () => void }) {
  const { t } = useI18n()
  const [cfg, setCfg] = useState<ScheduleConfig>(initial)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<unknown>()
  const set = (patch: Partial<ScheduleConfig>) => { setDirty(true); setCfg({ ...cfg, ...patch }) }
  const save = async () => {
    try { setCfg(await api.saveSchedule(slug, check, cfg)); setDirty(false); setError(undefined) } catch (err) { setError(err) }
  }
  return (
    <div className="card check-card">
      <h2>{t(`mt.check.${check}`)}</h2>
      <p className="muted small">{t(`mt.check.${check}Hint`)}</p>
      <ErrorBox error={error} />
      <div className="schedule-row">
        <label>
          {t('mt.cadence')}
          <select value={cfg.cadence} onChange={(e) => set({ cadence: e.target.value as ScheduleConfig['cadence'] })}>
            {(['off', 'daily', 'weekly'] as const).map((c) => <option key={c} value={c}>{t(`mt.cadence.${c}`)}</option>)}
          </select>
        </label>
        {cfg.cadence === 'weekly' && (
          <label>
            {t('mt.weekday')}
            <select value={cfg.weekday} onChange={(e) => set({ weekday: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5, 6, 0].map((d) => <option key={d} value={d}>{t(`mt.day.${d}`)}</option>)}
            </select>
          </label>
        )}
        {cfg.cadence !== 'off' && (
          <label>
            {t('mt.at')}
            <input type="time" value={cfg.time} onChange={(e) => set({ time: e.target.value })} />
          </label>
        )}
      </div>
      {!dirty && cfg.next_run && <p className="muted small">{t('mt.next', { time: formatTime(cfg.next_run) })}</p>}
      <div className="actions">
        <button className={dirty ? 'primary' : ''} disabled={!dirty} onClick={save}>{t('mt.saveSchedule')}</button>
        <button onClick={onRun}>{t('mt.runNow')}</button>
      </div>
    </div>
  )
}

function ReportRow({ r }: { r: ReportSummary }) {
  const { t } = useI18n()
  const [report, setReport] = useState<MaintenanceReport | null>()
  const load = (opened: boolean) => {
    if (opened && !report && r.status === 'completed') api.report(r).then(setReport, () => undefined)
  }
  return (
    <details className="card report" onToggle={(e) => load(e.currentTarget.open)}>
      <summary>
        <strong>{r.check ? t(`mt.check.${r.check}`) : r.workflow_id}</strong>
        {' · '}<span className="muted">{formatTime(r.started_at)} · {t('mt.by', { name: r.requested_by })}</span>
        {' · '}{r.status === 'running' ? <span className="muted">{t('mt.running')}</span> : r.summary}
      </summary>
      {report && (
        <>
          {report.proposals.length > 0 && (
            <p>{t('mt.openedProposals')}: {report.proposals.map((p) => <Link key={p} to={`/proposals/${p}`} className="tag">{p}</Link>)}</p>
          )}
          {report.findings.length === 0 ? (
            <p className="muted">{t('mt.noFindings')}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t('mt.col.severity')}</th><th>{t('mt.col.kind')}</th><th>{t('mt.col.path')}</th><th>{t('mt.col.message')}</th></tr></thead>
                <tbody>
                  {report.findings.map((f, i) => (
                    <tr key={i}>
                      <td><span className={`badge sev-${f.severity}`}>{f.severity}</span></td>
                      <td className="nowrap">{f.kind}</td>
                      <td><code className="path">{f.path}</code></td>
                      <td>{f.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </details>
  )
}
