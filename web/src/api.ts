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
}

export interface Proposal {
  id: string
  bundle: string
  title: string
  text: string
  submitted_by: string
  state: ProposalState
  changes: ArticleChange[]
  error: string | null
  commit: string | null
  reviewer: string | null
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
export interface ArticleSummary { path: string; title: string; type: string; status: string }
export interface BundleDetail extends BundleSummary { head: string | null; articles: ArticleSummary[] }
export interface AppConfig { temporal_ui_url: string; namespace: string }

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
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
  createBundle: (b: { slug: string; name: string; language: string }) =>
    request<BundleSummary>('POST', '/api/bundles', b),
  proposals: (filter: { bundle?: string; state?: string }) => {
    const q = new URLSearchParams(Object.entries(filter).filter(([, v]) => v) as [string, string][])
    return request<ProposalSummary[]>('GET', `/api/proposals?${q}`)
  },
  proposal: (id: string) => request<Proposal>('GET', `/api/proposals/${id}`),
  createProposal: (p: { bundle: string; title: string; text: string; submitted_by: string }) =>
    request<ProposalSummary>('POST', '/api/proposals', p),
  decide: (id: string, changeId: string, decision: Decision) =>
    request<Proposal>('POST', `/api/proposals/${id}/changes/${changeId}/decision`, { decision }),
  submit: (id: string, reviewer: string) => request<Proposal>('POST', `/api/proposals/${id}/submit`, { reviewer }),
}
