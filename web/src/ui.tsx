import type { ProposalState } from './api'
import { useI18n } from './i18n'

export function StateBadge({ state }: { state: ProposalState | string }) {
  const { t } = useI18n()
  return <span className={`badge state-${state}`}>{t(`state.${state}`)}</span>
}

export function ErrorBox({ error }: { error: unknown }) {
  const { t } = useI18n()
  if (!error) return null
  return <div className="error">{t('common.error')}: {error instanceof Error ? error.message : String(error)}</div>
}

export function formatTime(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

/** Compact date for dense lists: time only for today, otherwise month and day. */
export function formatShortTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date().toDateString() === d.toDateString()
  return today
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}
