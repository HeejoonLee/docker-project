import { parse as parseYaml } from 'yaml'
import type { Proposal, SourceInfo } from '../../api'
import { splitFrontmatter } from '../../markdown'

/** A Proposal's Sources followed by its Request (or audit instructions), in the order the agent saw them. */
export function proposalItems(p: Proposal): SourceInfo[] {
  return [...p.sources, ...(p.request ? [p.request] : [])]
}

/** Ids of this Proposal's Sources that an Article cites in its `sources` frontmatter. */
export function citedIds(content: string, items: SourceInfo[]): string[] {
  const ids = new Set(items.map((i) => i.id))
  let meta: unknown
  try {
    meta = parseYaml(splitFrontmatter(content).meta)
  } catch {
    return []
  }
  const list = (meta as { sources?: unknown } | null)?.sources
  if (!Array.isArray(list)) return []
  return list.map((s) => String((s as { id?: unknown })?.id ?? '')).filter((id) => ids.has(id))
}

/** Short label: Sources by their number, the Request by its kind. */
export function itemLabel(p: Proposal, item: SourceInfo, kindLabel: (kind: string) => string): string {
  const n = p.sources.findIndex((s) => s.id === item.id)
  return n >= 0 ? `${n + 1}` : kindLabel(item.kind)
}
