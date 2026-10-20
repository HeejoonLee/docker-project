import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { diffLines } from 'diff'

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
      {meta && <pre className="frontmatter">{meta}</pre>}
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
