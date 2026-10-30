import type { ArticleChange } from '../../api'

export type ChangeGroup = { dir: string; changes: ArticleChange[] }

/** Group Article changes by parent folder, folders in order of first appearance, files in Proposal order. */
export function groupByFolder(changes: ArticleChange[]): ChangeGroup[] {
  const groups = new Map<string, ArticleChange[]>()
  for (const c of changes) {
    const slash = c.path.lastIndexOf('/')
    const dir = slash === -1 ? '' : c.path.slice(0, slash)
    groups.set(dir, [...(groups.get(dir) ?? []), c])
  }
  return [...groups].map(([dir, items]) => ({ dir, changes: items }))
}

/** The order the sidebar shows Article changes in; numbering and "next undecided" follow it. */
export function displayOrder(changes: ArticleChange[]): ArticleChange[] {
  return groupByFolder(changes).flatMap((g) => g.changes)
}
