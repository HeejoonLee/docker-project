import { Link, useSearchParams } from 'react-router-dom'
import { useI18n } from '../i18n'
import { frontMatter, MermaidChart, usePalette, type Palette } from '../MermaidChart'

// One chart per Temporal workflow in src/stonepedia/workflows.py, plus an overview.
// tests/test_how_it_works.py fails if a workflow class is missing here.

type Kind = 'reviewer' | 'ai' | 'git' | 'system' | 'fail' | 'ok' | 'neutral'
type T = (key: string) => string

type Chart = {
  key: string
  workflow?: string
  kinds: Kind[]
  build: (t: T) => string
}

/** A quoted Mermaid label; "\n" becomes a line break. */
const q = (s: string) => `"${s.replace(/"/g, '#quot;').replace(/\n/g, '<br/>')}"`

function classDefs(p: Palette): string {
  const def = (kind: Kind, fill: string, stroke: string, color: string, extra = '') =>
    `  classDef ${kind} fill:${fill},stroke:${stroke},color:${color},stroke-width:1.5px${extra}`
  return [
    def('reviewer', p.personBg, p.person, p.text),
    def('ai', p.warnBg, p.warn, p.text),
    def('git', p.surface, p.accent, p.text, ',stroke-width:2px'),
    def('system', p.surface2, p.borderStrong, p.text),
    def('fail', p.badBg, p.bad, p.bad, ',stroke-dasharray:5 4'),
    def('ok', p.okBg, p.ok, p.ok),
    def('neutral', p.surface2, p.border, p.text2),
  ].join('\n')
}

const CHARTS: Chart[] = [
  {
    key: 'overview',
    kinds: ['reviewer', 'ai', 'git', 'system'],
    build: (t) => `flowchart TD
  reviewer([${q(t('hiw.o.reviewer'))}]):::reviewer
  schedule([${q(t('hiw.o.schedule'))}]):::system
  maintenance[${q(t('hiw.o.maintenance') + '\nMaintenanceWorkflow')}]:::system
  report[/${q(t('hiw.o.report'))}/]:::neutral
  proposal[${q(t('hiw.o.proposal') + '\nProposalWorkflow')}]:::ai
  bundle[${q(t('hiw.o.bundle') + '\nBundleWorkflow')}]:::git
  remote[(${q(t('hiw.o.remote'))})]:::git
  agentcheck[${q(t('hiw.o.agentCheck') + '\nAgentCheckWorkflow')}]:::system
  reviewer -->|${q(t('hiw.o.starts'))}| proposal
  reviewer -->|${q(t('hiw.o.runsNow'))}| maintenance
  schedule -->|${q(t('hiw.o.onSchedule'))}| maintenance
  maintenance -->|${q(t('hiw.o.refreshes'))}| proposal
  maintenance --> report
  proposal -->|${q(t('hiw.o.commits'))}| bundle
  reviewer -->|${q(t('hiw.o.configures'))}| bundle
  bundle -->|${q(t('hiw.o.pushes'))}| remote
  reviewer -.->|${q(t('hiw.o.tests'))}| agentcheck`,
  },
  {
    key: 'proposal',
    workflow: 'ProposalWorkflow',
    kinds: ['reviewer', 'ai', 'git', 'system', 'fail', 'ok', 'neutral'],
    build: (t) => `flowchart TD
  s_new[${q(t('hiw.p.new'))}]:::reviewer
  s_audit[${q(t('hiw.p.audit'))}]:::reviewer
  s_refresh[${q(t('hiw.p.refresh'))}]:::system
  s_new & s_audit & s_refresh --> read[${q(t('hiw.p.read'))}]:::system
  read -.->|${q(t('hiw.p.unreadable'))}| failed([${q(t('state.failed'))}]):::fail
  read --> propose[${q(t('hiw.p.propose'))}]:::ai
  propose -.->|${q(t('hiw.p.nothing'))}| failed
  propose --> review{{${q(t('state.awaiting_review'))}}}:::reviewer
  review -->|${q(t('hiw.p.decide'))}| review
  review -->|${q(t('hiw.p.askAgain'))}| rework[${q(t('hiw.p.rework'))}]:::ai
  rework -->|${q(t('hiw.p.newVersion'))}| review
  review -->|${q(t('hiw.p.submit'))}| anyAccepted{${q(t('hiw.p.anyAccepted'))}}:::system
  anyAccepted -->|${q(t('hiw.no'))}| discarded([${q(t('state.discarded'))}]):::neutral
  anyAccepted -->|${q(t('hiw.yes'))}| codeSame{${q(t('hiw.p.codeSame'))}}:::system
  codeSame -.->|${q(t('hiw.p.codeChanged'))}| review
  codeSame -->|${q(t('hiw.yes'))}| commit[${q(t('hiw.p.commit'))}]:::git
  commit -.->|${q(t('hiw.p.stale'))}| review
  commit --> done_([${q(t('state.done'))}]):::ok`,
  },
  {
    key: 'bundle',
    workflow: 'BundleWorkflow',
    kinds: ['reviewer', 'git', 'system', 'fail'],
    build: (t) => `flowchart TD
  created([${q(t('hiw.b.created'))}]):::reviewer --> init[${q(t('hiw.b.init'))}]:::git
  init --> hasRemote{${q(t('hiw.b.hasRemote'))}}:::system
  wait((${q(t('hiw.b.wait'))})):::system
  wait -->|${q(t('hiw.b.commitReq'))}| sync[${q(t('hiw.b.sync'))}]:::git
  wait -->|${q(t('hiw.b.saveReq'))}| sync
  sync --> write[${q(t('hiw.b.write'))}]:::git
  write --> hasRemote
  wait -->|${q(t('hiw.b.remoteReq'))}| setRemote[${q(t('hiw.b.setRemote'))}]:::git
  setRemote --> hasRemote
  hasRemote -->|${q(t('hiw.no'))}| wait
  hasRemote -->|${q(t('hiw.yes'))}| push[${q(t('hiw.b.push'))}]:::git
  push -->|${q(t('hiw.b.pushed'))}| wait
  push -.->|${q(t('hiw.b.pushFailed'))}| retry[${q(t('hiw.b.retry'))}]:::fail
  retry -.-> push
  wait -->|${q(t('hiw.b.retryReq'))}| push`,
  },
  {
    key: 'maintenance',
    workflow: 'MaintenanceWorkflow',
    kinds: ['reviewer', 'ai', 'system', 'fail', 'neutral'],
    build: (t) => `flowchart TD
  schedule([${q(t('hiw.m.schedule'))}]):::system --> which{${q(t('hiw.m.which'))}}:::system
  now([${q(t('hiw.m.now'))}]):::reviewer --> which
  which -->|${q(t('hiw.m.integrity'))}| scan[${q(t('hiw.m.scan'))}]:::system
  scan --> report1[/${q(t('hiw.m.report1'))}/]:::neutral
  which -->|${q(t('hiw.m.links'))}| fetch[${q(t('hiw.m.fetch'))}]:::system
  fetch -->|${q(t('hiw.m.changed'))}| open[${q(t('hiw.m.open'))}]:::ai
  open --> child[[${q(t('hiw.m.child'))}]]:::ai
  fetch -.->|${q(t('hiw.m.unreachable'))}| warn[${q(t('hiw.m.warn'))}]:::fail
  open --> report2[/${q(t('hiw.m.report2'))}/]:::neutral
  warn --> report2`,
  },
  {
    key: 'agent',
    workflow: 'AgentCheckWorkflow',
    kinds: ['reviewer', 'ai', 'system', 'fail', 'ok'],
    build: (t) => `flowchart LR
  test([${q(t('hiw.a.test'))}]):::reviewer --> fake{${q(t('hiw.a.fake'))}}:::system
  fake -->|${q(t('hiw.yes'))}| skip([${q(t('hiw.a.skip'))}]):::neutral
  fake -->|${q(t('hiw.no'))}| ask[${q(t('hiw.a.ask'))}]:::ai
  ask --> works([${q(t('hiw.a.works'))}]):::ok
  ask -.->|${q(t('hiw.a.noReply'))}| broken([${q(t('hiw.a.broken'))}]):::fail`,
  },
]

const STATES = ['generating', 'awaiting_review', 'committing', 'done', 'discarded', 'failed']

function Legend({ kinds }: { kinds: Kind[] }) {
  const { t } = useI18n()
  return (
    <ul className="hiw-legend">
      {kinds.map((kind) => <li key={kind}><span className={`hiw-swatch ${kind}`} />{t(`hiw.kind.${kind}`)}</li>)}
      <li><span className="hiw-dash" />{t('hiw.kind.dashed')}</li>
    </ul>
  )
}

export default function HowItWorks() {
  const { t } = useI18n()
  const palette = usePalette()
  const [params, setParams] = useSearchParams()
  const chart = CHARTS.find((c) => c.key === params.get('tab')) ?? CHARTS[0]
  return (
    <section className="hiw">
      <div className="page-head">
        <div>
          <h1>{t('hiw.title')}</h1>
          <p className="muted">{t('hiw.intro')}</p>
        </div>
      </div>
      <nav className="tabs page-tabs" aria-label={t('hiw.toc')}>
        {CHARTS.map((c) => (
          <button key={c.key} className={c.key === chart.key ? 'active' : ''} aria-pressed={c.key === chart.key} onClick={() => setParams({ tab: c.key })}>
            {t(`hiw.${c.key}.title`)}
          </button>
        ))}
      </nav>
      <article key={chart.key}>
        <p className="hiw-summary">
          {chart.workflow && <code className="hiw-workflow">{chart.workflow}</code>}
          {t(`hiw.${chart.key}.summary`)}
        </p>
        {chart.key === 'proposal' && (
          <p className="hiw-states small muted">
            {t('hiw.states')}{' '}
            {STATES.map((s) => <span key={s} className={`badge state-${s}`}>{t(`state.${s}`)}</span>)}
          </p>
        )}
        <div className="card hiw-card">
          <Legend kinds={chart.kinds} />
          <MermaidChart code={`${frontMatter(palette)}\n${chart.build(t)}\n${classDefs(palette)}`} label={t(`hiw.${chart.key}.title`)} />
        </div>
        {chart.key === 'overview' && <p className="small muted">{t('hiw.overview.more')} <Link to="/new">{t('hiw.overview.try')}</Link></p>}
      </article>
    </section>
  )
}
