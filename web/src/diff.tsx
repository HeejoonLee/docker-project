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
function hiddenRanges(unchanged: boolean[]): [number, number][] {
  const near = new Array(unchanged.length).fill(false)
  unchanged.forEach((same, i) => {
    if (same) return
    for (let j = Math.max(0, i - CONTEXT); j <= Math.min(unchanged.length - 1, i + CONTEXT); j++) near[j] = true
  })
  const ranges: [number, number][] = []
  for (let i = 0; i < unchanged.length; i++) {
    if (near[i]) continue
    const start = i
    while (i < unchanged.length && !near[i]) i++
    ranges.push([start, i])
  }
  return ranges
}

type SplitRow = { left?: Row; right?: Row; same: boolean }

/** Line up removed lines on the left with the added lines that replace them on the right. */
function toSplit(rows: Row[]): SplitRow[] {
  const out: SplitRow[] = []
  let i = 0
  while (i < rows.length) {
    if (rows[i].kind === 'ctx') {
      out.push({ left: rows[i], right: rows[i], same: true })
      i++
      continue
    }
    const dels: Row[] = []
    const adds: Row[] = []
    while (i < rows.length && rows[i].kind === 'del') dels.push(rows[i++])
    while (i < rows.length && rows[i].kind === 'add') adds.push(rows[i++])
    for (let j = 0; j < Math.max(dels.length, adds.length); j++) out.push({ left: dels[j], right: adds[j], same: false })
  }
  return out
}

function Segments({ segs }: { segs: Seg[] }) {
  return <>{segs.map((s, j) => (s.changed ? <mark key={j}>{s.text}</mark> : <Fragment key={j}>{s.text}</Fragment>))}</>
}

export type DiffMode = 'split' | 'unified'

/**
 * A diff with a little context around each change and the rest folded behind clickable bars:
 * side by side like VS Code's diff editor, or unified like GitHub.
 */
export function DiffView({ before, after, mode = 'unified' }: { before: string; after: string; mode?: DiffMode }) {
  const { t } = useI18n()
  const rows = useMemo(() => buildRows(before, after), [before, after])
  const split = useMemo(() => toSplit(rows), [rows])
  const lines = mode === 'split' ? split : rows
  const ranges = useMemo(
    () => hiddenRanges(mode === 'split' ? split.map((r) => r.same) : rows.map((r) => r.kind === 'ctx')),
    [mode, rows, split],
  )
  const [shown, setShown] = useState<Set<number>>(new Set())

  if (rows.every((r) => r.kind === 'ctx')) return <p className="muted">{t('diff.none')}</p>

  const gapAt = new Map(ranges.filter(([s]) => !shown.has(s)).map(([s, e]) => [s, e]))
  const body: ReactNode[] = []
  for (let i = 0; i < lines.length; i++) {
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
    if (mode === 'split') {
      const { left, right, same } = split[i]
      body.push(
        <tr key={i} className={same ? 'ctx' : 'chg'}>
          <td className={`ln${left && !same ? ' del' : ''}`}>{left?.old ?? ''}</td>
          <td className={`code${same ? '' : left ? ' del' : ' empty'}`}>{left && <Segments segs={left.segs} />}</td>
          <td className={`ln${right && !same ? ' add' : ''}`}>{right?.new ?? ''}</td>
          <td className={`code${same ? '' : right ? ' add' : ' empty'}`}>{right && <Segments segs={right.segs} />}</td>
        </tr>,
      )
      continue
    }
    const r = rows[i]
    body.push(
      <tr key={i} className={r.kind}>
        <td className="ln">{r.old ?? ''}</td>
        <td className="ln">{r.new ?? ''}</td>
        <td className="sign">{r.kind === 'add' ? '+' : r.kind === 'del' ? '−' : ''}</td>
        <td className="code"><Segments segs={r.segs} /></td>
      </tr>,
    )
  }
  return (
    <table className={`diff${mode === 'split' ? ' diff-split' : ''}`}>
      {mode === 'split' && (
        <colgroup><col className="col-ln" /><col /><col className="col-ln" /><col /></colgroup>
      )}
      <tbody>{body}</tbody>
    </table>
  )
}
