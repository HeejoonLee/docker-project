import type { GitCredentials } from './api'
import { useI18n } from './i18n'

export function GitCredentialsFields({ value, onChange, configured = false }: {
  value: GitCredentials
  onChange: (patch: Partial<GitCredentials>) => void
  configured?: boolean
}) {
  const { t } = useI18n()
  return (
    <>
      <label>
        {t('git.username')}
        <span className="hint">{t('git.usernameHint')}</span>
        <input autoComplete="off" value={value.git_username ?? ''} placeholder="oauth2"
          onChange={(e) => onChange({ git_username: e.target.value })} />
      </label>
      <label>
        {t('git.token')}
        <span className="hint">{t('git.tokenHint')}</span>
        {configured && <span className="hint">{t('git.tokenSaved')}</span>}
        <input type="password" autoComplete="new-password" value={value.git_token ?? ''}
          disabled={value.remove_git_token}
          onChange={(e) => onChange({ git_token: e.target.value })} />
      </label>
      {configured && (
        <label className="check">
          <input type="checkbox" checked={value.remove_git_token ?? false}
            onChange={(e) => onChange({ remove_git_token: e.target.checked, git_token: '' })} />
          <span>{t('git.removeToken')}</span>
        </label>
      )}
    </>
  )
}
