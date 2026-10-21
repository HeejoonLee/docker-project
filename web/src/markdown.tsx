import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { diffLines } from 'diff'
import { useState } from 'react'
import { parse as parseYaml } from 'yaml'
import { useI18n } from './i18n'

export function splitFrontmatter(text: string): { meta: string; body: string } {
  if (!text.startsWith('---\n')) return { meta: '', body: text }
  const end = text.indexOf('\n---\n', 3)
  if (end === -1) return { meta: '', body: text }
  return { meta: text.slice(4, end + 1), body: text.slice(end + 5) }
}

export function ArticleView({ content }: { content: string }) {
  const { meta, body } = splitFrontmatter(content)
  const html = DOMPurify.sanitize(marked.parse(body, { async: false }))
  return (
    <div className="article">
      {meta && <Frontmatter meta={meta} />}
      <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}

export function DiffView({ before, after }: { before: string; after: string }) {
  const parts = diffLines(before, after)
  return (
    <pre className="diff">
      {parts.map((p, i) => (
        <span key={i} className={p.added ? 'add' : p.removed ? 'del' : 'ctx'}>
          {p.value.replace(/\n$/, '').split('\n').map((line) => `${p.added ? '+' : p.removed ? '-' : ' '} ${line}`).join('\n') + '\n'}
        </span>
      ))}
    </pre>
  )
}

type Yaml = unknown
const isObject = (v: Yaml): v is Record<string, Yaml> => typeof v === 'object' && v !== null && !Array.isArray(v)
const isScalar = (v: Yaml) => v === null || typeof v !== 'object'

// Shown above the fold; everything else goes into the collapsible field list.
const HEADLINE = ['type', 'status', 'description', 'tags']

function Frontmatter({ meta }: { meta: string }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  let data: Yaml
  try {
    data = parseYaml(meta)
  } catch {
    data = undefined
  }
  if (!isObject(data)) return <pre className="frontmatter">{meta}</pre>

  const rest = Object.entries(data).filter(([k]) => !HEADLINE.includes(k))
  const tags = Array.isArray(data.tags) ? data.tags : []
  return (
    <div className="fm">
      <div className="fm-head">
        {data.type != null && <span className="badge fm-type">{String(data.type)}</span>}
        {data.status != null && <span className={`badge fm-status status-${String(data.status)}`}>{String(data.status)}</span>}
        {tags.map((x, i) => <span key={i} className="chip">{String(x)}</span>)}
      </div>
      {data.description != null && <p className="fm-desc">{String(data.description)}</p>}
      {rest.length > 0 && (
        <>
          <button className="link fm-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? '▾' : '▸'} {t('fm.properties', { count: String(rest.length) })}
          </button>
          {open && <Fields entries={rest} />}
        </>
      )}
    </div>
  )
}

function Fields({ entries }: { entries: [string, Yaml][] }) {
  return (
    <dl className="fm-fields">
      {entries.map(([k, v]) => (
        <div key={k} className={isScalar(v) ? 'fm-row' : 'fm-row fm-block'}>
          <dt>{k}</dt>
          <dd><Value v={v} /></dd>
        </div>
      ))}
    </dl>
  )
}

function Value({ v }: { v: Yaml }) {
  if (v === null || v === undefined || v === '') return <span className="muted">—</span>
  if (Array.isArray(v)) {
    if (v.length === 0) return <span className="muted">—</span>
    if (v.every(isScalar)) return <>{v.map((x, i) => <span key={i} className="chip">{String(x)}</span>)}</>
    return (
      <ol className="fm-list">
        {v.map((x, i) => <li key={i}>{isObject(x) ? <Fields entries={Object.entries(x)} /> : <Value v={x} />}</li>)}
      </ol>
    )
  }
  if (isObject(v)) return <Fields entries={Object.entries(v)} />
  if (typeof v === 'boolean') return <code>{String(v)}</code>
  return <>{String(v)}</>
}
