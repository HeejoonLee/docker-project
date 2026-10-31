import { useEffect, useRef, useState, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { LOCALES, useI18n } from '../i18n'
import { useUser } from '../user'
import { BrandMark as Mark } from '../BrandMark'

function Arrow({ diagonal = false }: { diagonal?: boolean }) {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d={diagonal ? 'M6 18 18 6M6 6h12v12' : 'M4 12h15m-6-6 6 6-6 6'} /></svg>
}

function Branch() {
  return <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="7" cy="5" r="2" /><circle cx="7" cy="19" r="2" /><circle cx="18" cy="6" r="2" /><path d="M7 7v10m11-9c0 7-11 2-11 9" /></svg>
}

function Stones() {
  return (
    <svg className="welcome-stones" aria-hidden="true" viewBox="0 0 600 600" fill="none">
      <defs>
        <linearGradient id="stone-bottom" x1="150" y1="350" x2="460" y2="490" gradientUnits="userSpaceOnUse"><stop stopColor="#aaa7a0" /><stop offset=".5" stopColor="#7c7a75" /><stop offset="1" stopColor="#41413e" /></linearGradient>
        <linearGradient id="stone-middle" x1="190" y1="240" x2="390" y2="370" gradientUnits="userSpaceOnUse"><stop stopColor="#dfbb94" /><stop offset=".55" stopColor="#c6956e" /><stop offset="1" stopColor="#9e6e4f" /></linearGradient>
        <linearGradient id="stone-top" x1="245" y1="140" x2="340" y2="250" gradientUnits="userSpaceOnUse"><stop stopColor="#e6dace" /><stop offset=".5" stopColor="#c5b9a8" /><stop offset="1" stopColor="#a29784" /></linearGradient>
        <radialGradient id="stone-shadow"><stop stopColor="#302e2a" stopOpacity=".18" /><stop offset="1" stopColor="#302e2a" stopOpacity="0" /></radialGradient>
      </defs>
      <circle cx="300" cy="300" r="192" stroke="#d7d2c8" opacity=".5" />
      <path d="M44 300h512M300 44v512" stroke="#d7d2c8" strokeDasharray="2 9" />
      {/* Raked-sand ripples spreading from the base of the stack. */}
      <g className="stone-ripples" stroke="#cdc7bc">
        <ellipse cx="302" cy="462" rx="220" ry="48" />
        <ellipse cx="302" cy="462" rx="220" ry="48" />
        <ellipse cx="302" cy="462" rx="220" ry="48" />
      </g>
      <g className="stone-orbit">
        <circle cx="300" cy="300" r="237" stroke="#d7d2c8" strokeDasharray="3 8" />
        <circle cx="99" cy="174" r="5" fill="#bb603d" /><circle cx="513" cy="405" r="5" fill="#706c64" />
        <circle cx="300" cy="63" r="3" fill="#b0a99e" />
      </g>
      <ellipse className="stone-shadow" cx="302" cy="479" rx="208" ry="35" fill="url(#stone-shadow)" />
      <g className="stone-stack">
        <g className="stone stone-bottom">
          <path d="M130 398c17-40 76-55 161-54 94 1 157 23 179 59 23 39-25 64-165 65-133 1-199-20-175-70Z" fill="url(#stone-bottom)" />
          <path d="M150 397c61-31 218-37 294 8" stroke="#d0cbc1" strokeOpacity=".35" />
        </g>
        <g className="stone stone-middle">
          <path d="M192 299c8-38 49-63 107-63 55 0 100 17 113 55 16 48-23 67-105 69-83 2-124-22-115-61Z" fill="url(#stone-middle)" />
          <path d="M208 291c46-29 115-32 180-4" stroke="#f1d9b4" strokeOpacity=".45" />
        </g>
        <g className="stone stone-top">
          <path d="M242 199c-1-36 23-65 57-65 35 0 62 29 62 60 0 34-25 49-60 49-33 0-58-13-59-44Z" fill="url(#stone-top)" />
          <path className="stone-glint" d="M257 176c17-23 48-28 70-10" stroke="#fff8eb" strokeOpacity=".5" />
        </g>
      </g>
      <path className="stone-sparkle" d="M447 130v16m-8-8h16" stroke="#969086" strokeWidth="1.5" />
      <path className="stone-sparkle stone-sparkle-late" d="M107 422v12m-6-6h12" stroke="#969086" strokeWidth="1.5" />
    </svg>
  )
}

function CycleIcon() {
  return <svg aria-hidden="true" width="34" height="34" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><g className="feature-cycle"><path d="M26 16a10 10 0 0 1-17.3 6.8M6 16A10 10 0 0 1 23.3 9.2" /><path d="M23.6 4.5v4.9h-4.9M8.4 27.5v-4.9h4.9" /></g><circle cx="16" cy="16" r="2.2" fill="currentColor" stroke="none" /></svg>
}

function BranchIcon() {
  return <svg aria-hidden="true" width="34" height="34" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path className="feature-draw" d="M9 9.5v13M24 10.5c0 9-15 3-15 12" /><circle cx="9" cy="7" r="2.5" /><circle cx="9" cy="25" r="2.5" /><circle className="feature-pop" cx="24" cy="8" r="2.5" /></svg>
}

function AgentsIcon() {
  return <svg aria-hidden="true" width="34" height="34" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M16 16 7 8m9 8 10-5m-10 5-2 11" strokeDasharray="2 3" className="feature-flow" /><circle cx="16" cy="16" r="3.5" fill="currentColor" fillOpacity=".15" /><circle className="feature-node" cx="7" cy="8" r="2.5" /><circle className="feature-node" cx="26" cy="11" r="2.5" /><circle className="feature-node" cx="14" cy="27" r="2.5" /></svg>
}

/** Fades sections in as they scroll into view. Content stays visible without JS or with reduced motion. */
function useReveal(root: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = root.current
    if (!el || !('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const targets = el.querySelectorAll('[data-reveal]')
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        entry.target.classList.add('revealed')
        observer.unobserve(entry.target)
      }
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 })
    el.classList.add('reveal-ready')
    targets.forEach((t) => observer.observe(t))
    return () => observer.disconnect()
  }, [root])
}

const STEPS = ['source', 'proposal', 'review', 'bundle'] as const

function Paper({ step, hidden = false }: { step: number; hidden?: boolean }) {
  const { t } = useI18n()
  const current = STEPS[step]
  return (
    <div className={hidden ? 'welcome-paper welcome-paper-ghost' : 'welcome-paper'} aria-hidden={hidden || undefined}>
      <div className="welcome-paper-top"><span>{t(`welcome.preview.${current}.label`)}</span><span aria-hidden="true">{step === 3 ? <Branch /> : ['↗', '✳', '✓'][step]}</span></div>
      <h3>{t('welcome.preview.title')}</h3>
      <div className={`welcome-excerpt excerpt-${current}`}><span aria-hidden="true">{step === 0 ? '“' : step === 1 ? '+' : '✓'}</span><p>{t(`welcome.preview.${current}.text`)}</p></div>
      <div className="welcome-paper-lines" aria-hidden="true"><i /><i /><i /></div>
      <div className="welcome-paper-footer"><span>{t(`welcome.preview.${current}.footer`)}</span><span className="welcome-example-status">{t(`welcome.preview.${current}.status`)}</span></div>
    </div>
  )
}

export default function Welcome() {
  const { t, lang, setLang } = useI18n()
  const { name } = useUser()
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)

  return (
    <div className="welcome" ref={root}>
      <a className="welcome-skip" href="#welcome-main">{t('welcome.skip')}</a>
      <header className="welcome-header">
        <Link to="/" className="welcome-brand" aria-label="Stonepedia"><Mark /><span>Stonepedia<span className="welcome-brand-dot">.</span></span></Link>
        <nav aria-label={t('nav.home')}>
          <a href="#how-it-works">{t('welcome.how')}</a>
          <a href="#built-to-last">{t('welcome.why')}</a>
        </nav>
        <div className="welcome-header-actions">
          <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
            {Object.entries(LOCALES).map(([code, locale]) => <option key={code} value={code}>{locale.label}</option>)}
          </select>
          <Link to="/inbox" className="welcome-nav-cta">{t('welcome.workspace')}<Arrow diagonal /></Link>
        </div>
      </header>

      <main id="welcome-main" className="welcome-main">
        <section className="welcome-hero" aria-labelledby="welcome-title">
          <div className="welcome-hero-copy">
            <h1 id="welcome-title">{t('welcome.title')}<br /><em>{t('welcome.titleAccent')}</em></h1>
            <p className="welcome-intro">{t('welcome.intro')}</p>
            <div className="welcome-hero-actions">
              <Link to="/bundles" className="welcome-button">{t(name ? 'welcome.bundles' : 'welcome.start')}<Arrow /></Link>
              <a href="#how-it-works" className="welcome-text-link">{t('welcome.seeHow')}<span aria-hidden="true">↓</span></a>
            </div>
          </div>
          <div className="welcome-art" role="img" aria-label={t('welcome.artAlt')}>
            <Stones />
            <div className="welcome-floating welcome-source"><span className="welcome-small-icon">↗</span><strong>{t('welcome.sourceValue')}</strong></div>
            <div className="welcome-floating welcome-reviewed"><span className="welcome-check">✓</span><strong>{t('welcome.reviewValue')}</strong></div>
            <div className="welcome-floating welcome-version"><Branch /><strong>{t('welcome.versionValue')}</strong></div>
          </div>
        </section>

        <div className="welcome-principles" data-reveal aria-label={t('welcome.principles')}>
          {['assisted', 'reviewed', 'versioned'].map((key, i) => <span key={key}><span className="welcome-principle-icon" aria-hidden="true">{['✳', '✓', '↗'][i]}</span>{t(`welcome.${key}`)}</span>)}
        </div>

        <section id="how-it-works" className="welcome-process" aria-labelledby="process-title">
          <div className="welcome-section-heading" data-reveal><h2 id="process-title">{t('welcome.processTitle')}<br /><em>{t('welcome.processAccent')}</em></h2><p>{t('welcome.processIntro')}<br /><Link to="/how-it-works" className="welcome-text-link">{t('welcome.allWorkflows')}<Arrow /></Link></p></div>
          <div className="welcome-process-layout" data-reveal>
            <div className="welcome-steps" aria-label={t('welcome.how')}>
              {STEPS.map((key, i) => (
                <button key={key} className={step === i ? 'welcome-step selected' : 'welcome-step'} aria-pressed={step === i} aria-controls="welcome-example" onClick={() => setStep(i)}>
                  <span className="welcome-step-number">0{i + 1}</span><span><strong>{t(`welcome.step.${key}`)}</strong><span>{t(`welcome.step.${key}Body`)}</span></span><span aria-hidden="true">↗</span>
                </button>
              ))}
            </div>
            <div id="welcome-example" className="welcome-example" aria-live="polite" aria-atomic="true">
              <div className="welcome-example-top"><span><span className="welcome-dot" />{t('welcome.example')}</span><span className="welcome-track" aria-hidden="true">{STEPS.map((key, i) => <i key={key} className={i <= step ? 'done' : undefined} />)}</span><span>0{step + 1} / 04</span></div>
              {/* Every step's card sits in the same cell, hidden, so the panel keeps the tallest card's height. */}
              <div className="welcome-paper-stack">
                {STEPS.map((key, i) => i === step ? null : <Paper key={`ghost-${key}`} step={i} hidden />)}
                <Paper key={current} step={step} />
              </div>
            </div>
          </div>
        </section>

        <section id="built-to-last" className="welcome-lasting" aria-labelledby="lasting-title">
          <div className="welcome-section-heading" data-reveal><h2 id="lasting-title">{t('welcome.lastingTitle')}<br /><em>{t('welcome.lastingAccent')}</em></h2></div>
          <div className="welcome-features" data-reveal>
            <article className="welcome-feature"><div className="welcome-feature-icon"><CycleIcon /></div><h3>{t('welcome.maintenanceTitle')}</h3><p>{t('welcome.maintenanceBody')}</p></article>
            <article className="welcome-feature"><div className="welcome-feature-icon"><BranchIcon /></div><h3>{t('welcome.ownershipTitle')}</h3><p>{t('welcome.ownershipBody')}</p></article>
            <article className="welcome-feature"><div className="welcome-feature-icon"><AgentsIcon /></div><h3>{t('welcome.agentsTitle')}</h3><p>{t('welcome.agentsBody')}</p></article>
          </div>
        </section>

        <section className="welcome-closing" data-reveal aria-labelledby="closing-title"><div className="welcome-closing-mark" aria-hidden="true"><Mark /></div><div className="welcome-closing-ring" aria-hidden="true" /><div><h2 id="closing-title">{t('welcome.closingTitle')}</h2><div className="welcome-hero-actions"><Link to="/bundles" className="welcome-button welcome-button-light">{t('welcome.start')}<Arrow /></Link><Link to="/inbox" className="welcome-text-link">{t('welcome.inbox')}<Arrow /></Link></div></div></section>
      </main>
      <footer className="welcome-footer"><Link to="/" className="welcome-brand"><Mark /><span>Stonepedia.</span></Link><a href="#welcome-main">{t('welcome.backTop')} ↑</a></footer>
    </div>
  )
}
