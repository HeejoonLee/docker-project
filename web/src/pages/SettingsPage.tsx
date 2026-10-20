import { useEffect, useState } from 'react'
import { api, type AgentCheck, type Settings } from '../api'
import { useI18n } from '../i18n'
import { ErrorBox } from '../ui'

export default function SettingsPage() {
  const { t } = useI18n()
  const [settings, setSettings] = useState<Settings>()
  const [error, setError] = useState<unknown>()
  const [saved, setSaved] = useState(false)
  const [check, setCheck] = useState<AgentCheck | 'running'>()

  useEffect(() => { api.settings().then(setSettings, setError) }, [])
  if (!settings) return error ? <ErrorBox error={error} /> : <p className="muted">{t('common.loading')}</p>

  let jsonError = ''
  try { JSON.parse(settings.claude_settings) } catch (e) { jsonError = (e as Error).message }

  const update = (next: Partial<Settings['app']>) => {
    setSaved(false)
    setSettings({ ...settings, app: { ...settings.app, ...next } })
  }
  const save = async () => {
    try {
      setSettings(await api.saveSettings(settings))
      setSaved(true)
      setError(undefined)
    } catch (err) {
      setError(err)
    }
  }
  const test = async () => {
    setCheck('running')
    try {
      await api.saveSettings(settings)
      setCheck(await api.testAgent())
    } catch (err) {
      setCheck({ ok: false, message: (err as Error).message, agent: settings.app.agent, seconds: 0 })
    }
  }

  return (
    <section>
      <h1>{t('settings.title')}</h1>
      <ErrorBox error={error} />
      <div className="form">
        <label>
          {t('settings.agent')}
          <select value={settings.app.agent} onChange={(e) => update({ agent: e.target.value as Settings['app']['agent'] })}>
            <option value="claude-cli">{t('settings.agent.claude')}</option>
            <option value="fake">{t('settings.agent.fake')}</option>
          </select>
        </label>
        <label>
          {t('settings.timeout')}
          <input
            type="number" min={1} max={600}
            value={settings.app.agent_timeout_minutes}
            onChange={(e) => update({ agent_timeout_minutes: Number(e.target.value) })}
          />
        </label>
        <label>
          {t('settings.claude')}
          <span className="hint">{t('settings.claudeHint')}</span>
          <textarea
            className="editor" rows={14} spellCheck={false}
            value={settings.claude_settings}
            onChange={(e) => { setSaved(false); setSettings({ ...settings, claude_settings: e.target.value }) }}
          />
          {jsonError && <span className="field-error">{t('settings.invalidJson')}: {jsonError}</span>}
        </label>
        <div className="actions">
          <button className="primary" disabled={!!jsonError} onClick={save}>{t('settings.save')}</button>
          <button disabled={!!jsonError || check === 'running'} onClick={test}>{t('settings.test')}</button>
          {saved && <span className="muted">{t('settings.saved')}</span>}
        </div>
        {check === 'running' && <p className="notice working">{t('settings.testing')}</p>}
        {check && check !== 'running' && (
          <p className={check.ok ? 'notice ok' : 'error'}>
            {t(check.ok ? 'settings.testOk' : 'settings.testFail', { seconds: String(check.seconds), message: check.message })}
          </p>
        )}
      </div>
    </section>
  )
}
