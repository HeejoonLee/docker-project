import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type BundleDetail, type BundleSettings, type FieldDef, type GitCredentials, type PushState, type Template } from '../api'
import { GitCredentialsFields } from '../GitCredentialsFields'
import { useI18n } from '../i18n'
import { ArticleView } from '../markdown'
import { ErrorBox, formatTime } from '../ui'
import { usePoll } from '../usePoll'
import { useUser } from '../user'

type Tab = 'articles' | 'settings' | 'template'

export default function BundlePage() {
  const { slug = '' } = useParams()
  const { t } = useI18n()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'articles'
  const bundle = usePoll(() => api.bundle(slug), slug, 5000)

  const b = bundle.data
  if (!b) return bundle.error ? <ErrorBox error={bundle.error} /> : <p className="muted">{t('common.loading')}</p>
  return (
    <section>
      <div className="page-head">
        <div>
          <h1>{b.name}</h1>
          <p className="muted">
            {b.slug} · {b.settings.language}{b.root !== '.' && <> · <code>{b.root}</code></>} · {t('bundles.head')}: <code>{b.head?.slice(0, 8)}</code>
          </p>
          <PushBadge slug={slug} push={b.push} onChange={bundle.reload} />
        </div>
        <Link className="button primary" to={`/new?bundle=${b.slug}`}>{t('nav.new')}</Link>
      </div>
      <nav className="tabs page-tabs">
        {(['articles', 'settings', 'template'] as const).map((k) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setParams({ tab: k })}>{t(`bundle.tab.${k}`)}</button>
        ))}
      </nav>
      {tab === 'articles' && <Articles b={b} />}
      {tab === 'settings' && <SettingsForm b={b} onSaved={(d) => bundle.setData(d)} />}
      {tab === 'template' && <TemplateEditor slug={slug} />}
    </section>
  )
}

function PushBadge({ slug, push, onChange }: { slug: string; push: PushState; onChange: () => void }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  if (push.state === 'off') return <p className="muted small">{t('push.off')}</p>
  if (push.state === 'ok') return <p className="small push-ok">✓ {t('push.ok', { at: formatTime(push.at) })}</p>
  if (push.state === 'pending') return <p className="small muted">{t('push.pending')}</p>
  return (
    <div className="error small">
      <strong>{t('push.failed')}</strong>: {push.error}
      {push.retry && <div className="muted">{t('push.autoRetry')}</div>}
      <div>
        <button disabled={busy} onClick={async () => { setBusy(true); await api.retryPush(slug).catch(() => undefined); setBusy(false); onChange() }}>
          {t('push.retry')}
        </button>
      </div>
    </div>
  )
}

function Articles({ b }: { b: BundleDetail }) {
  const { t } = useI18n()
  const [selected, setSelected] = useState<{ path: string; content: string }>()
  const [error, setError] = useState<unknown>()
  const open = (path: string) => api.article(b.slug, path).then(setSelected, setError)

  if (b.articles.length === 0) return <p className="muted">{t('bundles.noArticles')}</p>
  return (
    <>
      <ErrorBox error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('bundles.col.id')}</th>
              <th>{t('bundles.col.title')}</th>
              <th>{t('bundles.col.type')}</th>
              <th>{t('bundles.col.status')}</th>
              <th>{t('bundles.col.path')}</th>
            </tr>
          </thead>
          <tbody>
            {b.articles.map((a) => (
              <tr key={a.path} className={`${selected?.path === a.path ? 'selected' : ''} ${a.status === 'retired' ? 'retired' : ''}`}>
                <td className="nowrap">{a.id}</td>
                <td><button className="link" onClick={() => open(a.path)}>{a.title}</button></td>
                <td>{a.type}</td>
                <td>{a.status}</td>
                <td><code className="path">{a.path}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected && (
        <article className="change">
          <header><code className="path">{selected.path}</code></header>
          <div className="change-body"><ArticleView content={selected.content} /></div>
        </article>
      )}
    </>
  )
}

function SettingsForm({ b, onSaved }: { b: BundleDetail; onSaved: (d: BundleDetail) => void }) {
  const { t } = useI18n()
  const { name } = useUser()
  const [s, setS] = useState<BundleSettings>(b.settings)
  const [remote, setRemote] = useState(b.remote_url)
  const [branch, setBranch] = useState(b.branch)
  const [credentials, setCredentials] = useState<GitCredentials>({ git_username: b.git_username })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()
  const [saved, setSaved] = useState(false)
  const set = (patch: Partial<BundleSettings>) => { setSaved(false); setS({ ...s, ...patch }) }

  const save = async () => {
    setBusy(true)
    try {
      const updated = await api.saveBundleSettings(b.slug, { editor: name, settings: s, remote_url: remote, branch, ...credentials })
      onSaved(updated)
      setRemote(updated.remote_url)
      setCredentials({ git_username: updated.git_username, git_token: '', remove_git_token: false })
      setSaved(true)
      setError(undefined)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="form">
      <ErrorBox error={error} />
      <label>{t('bset.name')}<input value={s.name} onChange={(e) => set({ name: e.target.value })} /></label>
      <label>
        {t('bset.language')}
        <select value={s.language} onChange={(e) => set({ language: e.target.value })}>
          <option value="ko">한국어</option>
          <option value="en">English</option>
        </select>
      </label>
      <label>{t('bset.idPrefix')}<input value={s.id_prefix} onChange={(e) => set({ id_prefix: e.target.value })} /></label>
      <label>
        {t('bset.idField')}
        <span className="hint">{t('bset.idFieldHint')}</span>
        <input value={s.id_field} onChange={(e) => set({ id_field: e.target.value })} />
      </label>
      <label>{t('bset.idDigits')}<input type="number" min={1} max={6} value={s.id_digits} onChange={(e) => set({ id_digits: Number(e.target.value) })} /></label>
      <label className="check"><input type="checkbox" checked={s.generate_index} onChange={(e) => set({ generate_index: e.target.checked })} /><span>{t('bset.index')}</span></label>
      <label className="check"><input type="checkbox" checked={s.generate_manifest} onChange={(e) => set({ generate_manifest: e.target.checked })} /><span>{t('bset.manifest')}</span></label>
      <label>
        {t('bset.remote')}
        <span className="hint">{t('bundles.cloneUrlHint')}</span>
        <input value={remote} onChange={(e) => {
          setSaved(false)
          setRemote(e.target.value)
          setCredentials({ ...credentials, remove_git_token: false })
        }} />
      </label>
      <label>{t('bset.branch')}<input value={branch} onChange={(e) => { setSaved(false); setBranch(e.target.value) }} /></label>
      {b.git_token_configured && remote.trim() !== b.remote_url && <p className="hint">{t('git.newRemote')}</p>}
      <GitCredentialsFields value={credentials} configured={b.git_token_configured && remote.trim() === b.remote_url}
        onChange={(patch) => { setSaved(false); setCredentials({ ...credentials, ...patch }) }} />
      <p className="muted small">{t('bset.root')}: <code>{b.root}</code>{b.clone_url && <> · {b.clone_url}</>}</p>
      <div className="actions">
        <button className="primary" disabled={busy} onClick={save}>{t('bset.save')}</button>
        {saved && <span className="muted">{t('bset.saved')}</span>}
      </div>
    </div>
  )
}

function TemplateEditor({ slug }: { slug: string }) {
  const { t } = useI18n()
  const { name } = useUser()
  const [tmpl, setTmpl] = useState<Template>()
  const [error, setError] = useState<unknown>()
  const [saved, setSaved] = useState(false)

  useEffect(() => { api.template(slug).then(setTmpl, setError) }, [slug])
  if (!tmpl) return error ? <ErrorBox error={error} /> : <p className="muted">{t('common.loading')}</p>

  const update = (next: Template) => { setSaved(false); setTmpl(next) }
  const setType = (i: number, patch: Partial<Template['types'][number]>) =>
    update({ ...tmpl, types: tmpl.types.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
  const setField = (i: number, patch: Partial<FieldDef>) =>
    update({ ...tmpl, fields: tmpl.fields.map((x, j) => (j === i ? { ...x, ...patch } : x)) })

  const save = async () => {
    try {
      const clean: Template = {
        ...tmpl,
        types: tmpl.types.filter((x) => x.name.trim()),
        fields: tmpl.fields.filter((x) => x.name.trim()),
      }
      setTmpl(await api.saveTemplate(slug, name, clean))
      setSaved(true)
      setError(undefined)
    } catch (err) {
      setError(err)
    }
  }

  return (
    <div className="template-editor">
      <p className="muted">{t('tmpl.intro')}</p>
      <ErrorBox error={error} />
      <h2>{t('tmpl.types')}</h2>
      {tmpl.types.map((ty, i) => (
        <div key={i} className="card row-card">
          <div className="row">
            <label>{t('tmpl.typeName')}<input value={ty.name} onChange={(e) => setType(i, { name: e.target.value })} /></label>
            <button className="link" onClick={() => update({ ...tmpl, types: tmpl.types.filter((_, j) => j !== i) })}>{t('tmpl.remove')}</button>
          </div>
          <label>{t('tmpl.typeRule')}<textarea rows={2} value={ty.rule} onChange={(e) => setType(i, { rule: e.target.value })} /></label>
          <label>
            {t('tmpl.typeSections')}
            <input value={ty.sections.join(', ')} onChange={(e) => setType(i, { sections: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
          </label>
        </div>
      ))}
      <button onClick={() => update({ ...tmpl, types: [...tmpl.types, { name: '', rule: '', sections: [] }] })}>{t('tmpl.addType')}</button>

      <h2>{t('tmpl.fields')}</h2>
      <div className="table-wrap">
        <table className="fields">
          <thead>
            <tr><th>{t('tmpl.fieldName')}</th><th>{t('tmpl.writtenBy')}</th><th>{t('tmpl.required')}</th><th>{t('tmpl.fieldDesc')}</th><th /></tr>
          </thead>
          <tbody>
            {tmpl.fields.map((f, i) => (
              <tr key={i}>
                <td><input value={f.name} onChange={(e) => setField(i, { name: e.target.value })} /></td>
                <td>
                  <select aria-label={`${t('tmpl.writtenBy')}: ${f.name}`} value={f.written_by} onChange={(e) => setField(i, { written_by: e.target.value as FieldDef['written_by'] })}>
                    <option value="ai">{t('tmpl.writtenBy.ai')}</option>
                    <option value="system">{t('tmpl.writtenBy.system')}</option>
                  </select>
                </td>
                <td><input type="checkbox" checked={f.required} disabled={f.written_by === 'system'} onChange={(e) => setField(i, { required: e.target.checked })} /></td>
                <td><input className="wide" value={f.description} disabled={f.written_by === 'system'} onChange={(e) => setField(i, { description: e.target.value })} /></td>
                <td><button className="link" onClick={() => update({ ...tmpl, fields: tmpl.fields.filter((_, j) => j !== i) })}>{t('tmpl.remove')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={() => update({ ...tmpl, fields: [...tmpl.fields, { name: '', written_by: 'ai', required: false, description: '' }] })}>{t('tmpl.addField')}</button>

      <h2>{t('tmpl.guidance')}</h2>
      <textarea rows={6} value={tmpl.guidance} onChange={(e) => update({ ...tmpl, guidance: e.target.value })} />

      <div className="actions sticky-actions">
        <button className="primary" onClick={save}>{t('tmpl.save')}</button>
        <button onClick={() => api.template(slug, true).then(update, setError)}>{t('tmpl.infer')}</button>
        {saved && <span className="muted">{t('tmpl.saved')}</span>}
      </div>
    </div>
  )
}
