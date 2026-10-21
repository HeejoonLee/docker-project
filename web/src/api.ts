export type ProposalState = 'generating' | 'awaiting_review' | 'committing' | 'done' | 'discarded' | 'failed'
export type Decision = 'pending' | 'accepted' | 'discarded'

export interface ArticleChange {
  id: string
  path: string
  kind: 'create' | 'update' | 'retire'
  base_blob: string | null
  base_content: string | null
  content: string
  title: string
  decision: Decision
  stale: boolean
  edited_by: string | null
  history: { content: string; replaced_by: 'revise' | 'edit' | 'feedback'; note: string; by: string; at: string }[]
}

export type SourceKind = 'text' | 'file' | 'link' | 'request' | 'audit'

export interface SourceInfo {
  id: string
  kind: SourceKind
  title: string
  original: string
  filename: string
  url: string
  media: string
  pages: number | null
  text_chars: number
  warnings: string[]
  preview: string
}

export interface Proposal {
  id: string
  bundle: string
  title: string
  submitted_by: string
  source_kind: SourceKind
  source: SourceInfo | null
  targets: string[]
  state: ProposalState
  changes: ArticleChange[]
  error: string | null
  commit: string | null
  reviewer: string | null
  summary: string
  cost_usd: number
  runs: number
}

export interface ProposalSummary {
  id: string
  bundle: string
  title: string
  submitted_by: string
  state: ProposalState
  created_at: string | null
}

export interface BundleSummary { slug: string; name: string; language: string; created_at: string | null }
export interface ArticleSummary { path: string; id: string; title: string; type: string; status: string }
export interface BundleSettings {
  name: string
  language: string
  id_prefix: string
  id_field: string
  id_digits: number
  generate_index: boolean
  generate_manifest: boolean
}
export interface PushState { state: 'off' | 'ok' | 'pending' | 'failed'; error: string; retry: boolean; at: string }
export interface BundleDetail {
  slug: string
  name: string
  settings: BundleSettings
  root: string
  remote_url: string
  branch: string
  clone_url: string
  push: PushState
  head: string | null
  articles: ArticleSummary[]
}
export interface TypeDef { name: string; rule: string; sections: string[] }
export interface FieldDef { name: string; written_by: 'ai' | 'system'; required: boolean; description: string }
export interface Template { types: TypeDef[]; fields: FieldDef[]; guidance: string }
export type Check = 'integrity' | 'links'
export interface ScheduleConfig { cadence: 'off' | 'daily' | 'weekly'; time: string; weekday: number; next_run?: string | null }
export interface ReportSummary {
  workflow_id: string; run_id: string; check: Check | ''; requested_by: string
  started_at: string | null; status: string; summary: string
}
export interface Finding { severity: 'error' | 'warning'; kind: string; path: string; message: string }
export interface MaintenanceReport { bundle: string; check: Check; requested_by: string; findings: Finding[]; proposals: string[]; summary: string }
export interface MaintenanceOverview { timezone: string; schedules: Record<Check, ScheduleConfig>; reports: ReportSummary[] }
export interface NewBundle {
  slug: string; name: string; language: string; id_prefix: string
  clone_url: string; branch: string; root: string; remote_url: string
}
export interface AppConfig { temporal_ui_url: string; namespace: string }
export interface Settings {
  app: {
    agent: 'claude-cli' | 'fake'
    agent_timeout_minutes: number
    max_source_mb: number
    verify_link_certificates: boolean
  }
  claude_settings: string
}
export interface AgentCheck { ok: boolean; message: string; agent: string; seconds: number }

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData
  const res = await fetch(url, {
    method,
    headers: body === undefined || isForm ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* not JSON */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  config: () => request<AppConfig>('GET', '/api/config'),
  bundles: () => request<BundleSummary[]>('GET', '/api/bundles'),
  bundle: (slug: string) => request<BundleDetail>('GET', `/api/bundles/${slug}`),
  article: (slug: string, path: string) =>
    request<{ path: string; content: string }>('GET', `/api/bundles/${slug}/articles/${path}`),
  createBundle: (b: NewBundle) => request<BundleSummary>('POST', '/api/bundles', b),
  saveBundleSettings: (slug: string, body: { editor: string; settings: BundleSettings; remote_url: string; branch: string }) =>
    request<BundleDetail>('PUT', `/api/bundles/${slug}/settings`, body),
  template: (slug: string, inferred = false) =>
    request<Template>('GET', `/api/bundles/${slug}/template${inferred ? '?inferred=true' : ''}`),
  saveTemplate: (slug: string, editor: string, template: Template) =>
    request<Template>('PUT', `/api/bundles/${slug}/template`, { editor, template }),
  maintenance: (slug: string) => request<MaintenanceOverview>('GET', `/api/maintenance/${slug}`),
  saveSchedule: (slug: string, check: Check, cfg: ScheduleConfig) =>
    request<ScheduleConfig>('PUT', `/api/maintenance/${slug}/schedules/${check}`, cfg),
  runCheck: (slug: string, check: Check, requested_by: string) =>
    request<ReportSummary>('POST', `/api/maintenance/${slug}/run/${check}`, { requested_by }),
  report: (r: ReportSummary) =>
    request<MaintenanceReport | null>('GET', `/api/maintenance/reports/${encodeURIComponent(r.workflow_id)}/${r.run_id}`),
  audit: (slug: string, requested_by: string, focus: string) =>
    request<ProposalSummary>('POST', `/api/bundles/${slug}/audit`, { requested_by, focus }),
  retryPush: (slug: string) => request<PushState>('POST', `/api/bundles/${slug}/push`),
  proposals: (filter: { bundle?: string; state?: string }) => {
    const q = new URLSearchParams(Object.entries(filter).filter(([, v]) => v) as [string, string][])
    return request<ProposalSummary[]>('GET', `/api/proposals?${q}`)
  },
  proposal: (id: string) => request<Proposal>('GET', `/api/proposals/${id}`),
  createProposal: (p: {
    bundle: string; kind: SourceKind; title: string; submitted_by: string
    text?: string; url?: string; file?: File; targets?: string[]
  }) => {
    const form = new FormData()
    for (const [k, v] of Object.entries(p)) {
      if (v === undefined) continue
      if (k === 'targets') form.append(k, (v as string[]).join('\n'))
      else form.append(k, v as string | File)
    }
    return request<ProposalSummary>('POST', '/api/proposals', form)
  },
  sourceUrl: (id: string, name: string) => `/api/proposals/${id}/source/${encodeURIComponent(name)}`,
  decide: (id: string, changeId: string, decision: Decision) =>
    request<Proposal>('POST', `/api/proposals/${id}/changes/${changeId}/decision`, { decision }),
  revise: (id: string, changeId: string, feedback: string, reviewer: string) =>
    request<Proposal>('POST', `/api/proposals/${id}/changes/${changeId}/revise`, { feedback, reviewer }),
  edit: (id: string, changeId: string, content: string, editor: string) =>
    request<Proposal>('POST', `/api/proposals/${id}/changes/${changeId}/edit`, { content, editor }),
  feedback: (id: string, text: string, reviewer: string) =>
    request<Proposal>('POST', `/api/proposals/${id}/feedback`, { text, reviewer }),
  settings: () => request<Settings>('GET', '/api/settings'),
  saveSettings: (s: Settings) => request<Settings>('PUT', '/api/settings', s),
  testAgent: () => request<AgentCheck>('POST', '/api/settings/test'),
  submit: (id: string, reviewer: string) => request<Proposal>('POST', `/api/proposals/${id}/submit`, { reviewer }),
}
