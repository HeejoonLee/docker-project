import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useI18n } from '../i18n'
import { ArticleView } from '../markdown'
import { ErrorBox } from '../ui'
import { usePoll } from '../usePoll'

export default function BundlePage() {
  const { slug = '' } = useParams()
  const { t } = useI18n()
  const bundle = usePoll(() => api.bundle(slug), slug, 10000)
  const [selected, setSelected] = useState<{ path: string; content: string }>()
  const [error, setError] = useState<unknown>()

  const open = (path: string) => api.article(slug, path).then(setSelected, setError)

  const b = bundle.data
  if (!b) return bundle.error ? <ErrorBox error={bundle.error} /> : <p className="muted">{t('common.loading')}</p>
  return (
    <section>
      <div className="page-head">
        <div>
          <h1>{b.name}</h1>
          <p className="muted">
            {b.slug} · {b.language} · {t('bundles.head')}: <code>{b.head?.slice(0, 8)}</code>
          </p>
        </div>
        <Link className="button primary" to={`/new?bundle=${b.slug}`}>{t('nav.new')}</Link>
      </div>
      <ErrorBox error={error} />
      <h2>{t('bundles.articles')}</h2>
      {b.articles.length === 0 ? (
        <p className="muted">{t('bundles.noArticles')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('bundles.col.title')}</th>
                <th>{t('bundles.col.type')}</th>
                <th>{t('bundles.col.status')}</th>
                <th>{t('bundles.col.path')}</th>
              </tr>
            </thead>
            <tbody>
              {b.articles.map((a) => (
                <tr key={a.path} className={selected?.path === a.path ? 'selected' : ''}>
                  <td><button className="link" onClick={() => open(a.path)}>{a.title}</button></td>
                  <td>{a.type}</td>
                  <td>{a.status}</td>
                  <td><code className="path">{a.path}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <article className="change">
          <header><code className="path">{selected.path}</code></header>
          <div className="change-body"><ArticleView content={selected.content} /></div>
        </article>
      )}
    </section>
  )
}
