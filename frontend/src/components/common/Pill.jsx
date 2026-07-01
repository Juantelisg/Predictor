const STYLES = {
  alta:     { background: 'rgba(94,234,212,0.12)',  color: '#5eead4', border: 'rgba(94,234,212,0.25)' },
  media:    { background: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.25)' },
  baja:     { background: 'rgba(96,165,250,0.12)',  color: '#60a5fa', border: 'rgba(96,165,250,0.25)' },
  pass:     { background: 'rgba(255,255,255,0.04)', color: '#4d5e73', border: 'rgba(255,255,255,0.08)' },
  strong:   { background: 'rgba(94,234,212,0.12)',  color: '#5eead4', border: 'rgba(94,234,212,0.25)' },
  moderate: { background: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.25)' },
}

export default function Pill({ label, variant }) {
  const s = STYLES[variant?.toLowerCase()] || STYLES.pass
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 text-[11px] font-semibold rounded-md tabular"
      style={{ background: s.background, color: s.color, border: `1px solid ${s.border}` }}
    >
      {label}
    </span>
  )
}
