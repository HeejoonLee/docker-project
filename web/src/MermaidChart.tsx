import { useEffect, useId, useState } from 'react'
import { useI18n } from './i18n'

/** The app's colors, read from the CSS variables so charts follow light and dark mode. */
export type Palette = Record<
  'surface' | 'surface2' | 'text' | 'text2' | 'muted' | 'border' | 'borderStrong' | 'accent' | 'accentText'
  | 'person' | 'personBg' | 'ok' | 'okBg' | 'warn' | 'warnBg' | 'bad' | 'badBg',
  string
>

const VARS: Record<keyof Palette, string> = {
  surface: '--surface', surface2: '--surface-2', text: '--text', text2: '--text-2', muted: '--muted',
  border: '--border', borderStrong: '--border-strong', accent: '--accent', accentText: '--accent-text',
  person: '--person', personBg: '--person-bg', ok: '--ok', okBg: '--ok-bg',
  warn: '--warn', warnBg: '--warn-bg', bad: '--bad', badBg: '--bad-bg',
}

const FONT = '"Pretendard Variable", Pretendard, system-ui, -apple-system, "Segoe UI", "Noto Sans KR", sans-serif'

function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(
    Object.entries(VARS).map(([key, name]) => [key, style.getPropertyValue(name).trim()]),
  ) as Palette
}

/** The current palette; changes when the system switches between light and dark. */
export function usePalette(): Palette {
  const [palette, setPalette] = useState(readPalette)
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setPalette(readPalette())
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return palette
}

type Mermaid = typeof import('mermaid').default
let loading: Promise<Mermaid> | undefined
let queue: Promise<unknown> = Promise.resolve()

/** Front matter that styles a chart like the app. Part of the code, so copied code renders the same anywhere. */
export function frontMatter(p: Palette): string {
  const vars = {
    fontFamily: FONT, fontSize: '15px', background: p.surface, primaryColor: p.surface2, primaryTextColor: p.text,
    primaryBorderColor: p.borderStrong, secondaryColor: p.surface2, tertiaryColor: p.surface2, lineColor: p.muted,
    textColor: p.text2, clusterBkg: p.surface2, clusterBorder: p.border, edgeLabelBackground: p.surface, titleColor: p.text2,
  }
  return [
    '---',
    'config:',
    '  theme: base',
    '  layout: dagre', // Mermaid 12's default draws right-angled edges
    '  flowchart:',
    '    curve: basis',
    '    padding: 14',
    '    nodeSpacing: 40',
    '    rankSpacing: 50',
    '    wrappingWidth: 260',
    '  themeVariables:',
    ...Object.entries(vars).map(([k, v]) => `    ${k}: ${JSON.stringify(v)}`),
    '---',
  ].join('\n')
}

/** Mermaid is large, so it is only loaded once a chart is on screen. Renders run one at a time. */
function render(id: string, code: string): Promise<string> {
  loading ??= import('mermaid').then((m) => {
    m.default.initialize({ startOnLoad: false, securityLevel: 'strict' })
    return m.default
  })
  const job = queue.then(async () => (await (await loading!).render(id, code)).svg)
  queue = job.catch(() => undefined)
  return job
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard API needs a secure context; fall back for plain-http deployments.
    const area = document.createElement('textarea')
    area.value = text
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
}

export function MermaidChart({ code, label }: { code: string; label: string }) {
  const { t } = useI18n()
  const id = 'mmd-' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const [svg, setSvg] = useState<string>()
  const [error, setError] = useState<string>()
  const [showCode, setShowCode] = useState(false)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    let live = true
    render(id, code).then(
      (out) => { if (live) { setSvg(out); setError(undefined) } },
      (err) => { if (live) setError(String(err)) },
    )
    return () => { live = false }
  }, [id, code])

  const copy = async () => {
    await copyText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="mermaid-chart">
      <div className="mermaid-toolbar">
        <button className="small-button" aria-pressed={showCode} onClick={() => setShowCode((v) => !v)}>
          {showCode ? t('hiw.hideCode') : t('hiw.showCode')}
        </button>
        {showCode && <button className="small-button" onClick={copy}>{copied ? t('hiw.copied') : t('hiw.copy')}</button>}
      </div>
      {showCode && <pre className="mermaid-code"><code>{code}</code></pre>}
      {error ? (
        <p className="error small">{error}</p>
      ) : svg ? (
        <div className="mermaid-svg" role="img" aria-label={label} dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <div className="mermaid-placeholder muted small">{t('hiw.loadingChart')}</div>
      )}
    </div>
  )
}
