import { diffLines, diffWordsWithSpace } from 'diff'
import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { useI18n } from './i18n'

const CONTEXT = 3

type Kind = 'ctx' | 'add' | 'del'
type Seg = { text: string; changed: boolean }
type Row = { kind: Kind; old?: number; new?: number; segs: Seg[] }

function splitLines(value: string): string[] {
  return value.replace(/\n$/, '').split('\n')
}

/** Word-level highlight for a removed/added line pair, skipped when the lines are mostly different. */
function pairSegments(before: string, after: string): [Seg[], Seg[]] | null {
  const parts = diffWordsWithSpace(before, after)
  const same = parts.filter((p) => !p.added && !p.removed).reduce((n, p) => n + p.value.length, 0)
  if (same < 0.4 * Math.max(before.length, after.length)) return null
  return [
    parts.filter((p) => !p.added).map((p) => ({ text: p.value, changed: !!p.removed })),
    parts.filter((p) => !p.removed).map((p) => ({ text: p.value, changed: !!p.added })),
  ]
}

function buildRows(before: string, after: string): Row[] {
  const rows: Row[] = []
  let o = 1
  let n = 1
  const parts = diffLines(before, after)
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i]
    const lines = splitLines(p.value)
    if (p.removed && parts[i + 1]?.added) {
      // A replaced block: pair lines up for word highlighting.
      const added = splitLines(parts[i + 1].value)
      const pairs = lines.map((line, j) => (j < added.length ? pairSegments(line, added[j]) : null))
      lines.forEach((line, j) => rows.push({ kind: 'del', old: o++, segs: pairs[j]?.[0] ?? [{ text: line, changed: false }] }))
      added.forEach((line, j) => rows.push({ kind: 'add', new: n++, segs: pairs[j]?.[1] ?? [{ text: line, changed: false }] }))
      i++
    } else if (p.removed) {
      lines.forEach((line) => rows.push({ kind: 'del', old: o++, segs: [{ text: line, changed: false }] }))
    } else if (p.added) {
      lines.forEach((line) => rows.push({ kind: 'add', new: n++, segs: [{ text: line, changed: false }] }))
    } else {
      lines.forEach((line) => rows.push({ kind: 'ctx', old: o++, new: n++, segs: [{ text: line, changed: false }] }))
    }
  }
  return rows
}

/** Runs of unchanged rows further than CONTEXT lines from any change, as [start, end) ranges. */
function hiddenRanges(rows: Row[]): [number, number][] {
  const near = new Array(rows.length).fill(false)
  rows.forEach((r, i) => {
    if (r.kind === 'ctx') return
    for (let j = Math.max(0, i - CONTEXT); j <= Math.min(rows.length - 1, i + CONTEXT); j++) near[j] = true
  })
  const ranges: [number, number][] = []
  for (let i = 0; i < rows.length; i++) {
    if (near[i]) continue
    const start = i
    while (i < rows.length && !near[i]) i++
    ranges.push([start, i])
  }
  return ranges
}

/** A GitHub-style unified diff: changes with a little context, the rest folded behind clickable bars. */
export function DiffView({ before, after }: { before: string; after: string }) {
  const { t } = useI18n()
  const rows = useMemo(() => buildRows(before, after), [before, after])
  const ranges = useMemo(() => hiddenRanges(rows), [rows])
  const [shown, setShown] = useState<Set<number>>(new Set())

  if (rows.every((r) => r.kind === 'ctx')) return <p className="muted">{t('diff.none')}</p>

  const gapAt = new Map(ranges.filter(([s]) => !shown.has(s)).map(([s, e]) => [s, e]))
  const body: ReactNode[] = []
  for (let i = 0; i < rows.length; i++) {
    const end = gapAt.get(i)
    if (end !== undefined) {
      const start = i
      body.push(
        <tr key={`gap-${start}`} className="gap">
          <td colSpan={4}>
            <button className="gap-button" onClick={() => setShown(new Set(shown).add(start))}>
              ⋯ {t('diff.unchanged', { count: String(end - start) })}
            </button>
          </td>
        </tr>,
      )
      i = end - 1
      continue
    }
    const r = rows[i]
    body.push(
      <tr key={i} className={r.kind}>
        <td className="ln">{r.old ?? ''}</td>
        <td className="ln">{r.new ?? ''}</td>
        <td className="sign">{r.kind === 'add' ? '+' : r.kind === 'del' ? '−' : ''}</td>
        <td className="code">
          {r.segs.map((s, j) => (s.changed ? <mark key={j}>{s.text}</mark> : <Fragment key={j}>{s.text}</Fragment>))}
        </td>
      </tr>,
    )
  }
  return (
    <table className="diff">
      <tbody>{body}</tbody>
    </table>
  )
}
