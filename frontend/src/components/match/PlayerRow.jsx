const POS_CONFIG = {
  forward:    { label: 'FWD', bg: 'rgba(251,113,133,0.14)', color: '#fb7185' },
  midfielder: { label: 'MID', bg: 'rgba(96,165,250,0.14)',  color: '#60a5fa' },
  defender:   { label: 'DEF', bg: 'rgba(255,255,255,0.06)', color: '#8892a4' },
  goalkeeper: { label: 'GK',  bg: 'rgba(251,191,36,0.13)',  color: '#fbbf24' },
}

function HitBar({ rate }) {
  if (rate == null) return <span className="text-xs text-subtle tabular w-16 text-center">—</span>
  const w = Math.min(100, Math.max(0, rate))
  const barColor = rate >= 80 ? ['rgba(251,113,133,0.7)', '#fb7185']
    : rate >= 60 ? ['rgba(94,234,212,0.7)', '#5eead4']
    : rate >= 40 ? ['rgba(96,165,250,0.6)', '#60a5fa']
    : ['rgba(77,94,115,0.5)', '#4d5e73']
  const textColor = rate >= 80 ? '#fb7185' : rate >= 60 ? '#5eead4' : rate >= 40 ? '#60a5fa' : '#4d5e73'

  return (
    <div className="flex items-center gap-1.5 w-16">
      <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: w + '%',
            background: `linear-gradient(90deg, ${barColor[0]}, ${barColor[1]})`,
          }}
        />
      </div>
      <span className="text-xs font-semibold tabular w-7 text-right" style={{ color: textColor }}>
        {rate}%
      </span>
    </div>
  )
}

function ReadBadge({ read }) {
  if (!read) return null
  const s = read.includes('alto') ? { bg: 'rgba(251,113,133,0.14)', color: '#fb7185' }
    : read.includes('buena') || read.includes('constante') ? { bg: 'rgba(94,234,212,0.1)', color: '#5eead4' }
    : read.includes('bajo') ? { bg: 'rgba(255,255,255,0.04)', color: '#4d5e73' }
    : { bg: 'rgba(255,255,255,0.06)', color: '#8892a4' }
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0"
      style={{ background: s.bg, color: s.color }}
    >
      {read}
    </span>
  )
}

export default function PlayerRow({ player }) {
  const { who, market, side, line, l5, l10, season, read, position } = player
  const overLabel = side === 'over' ? `Over ${line}` : side === 'under' ? `Under ${line}` : String(line ?? '')
  const posCfg = POS_CONFIG[position?.toLowerCase()]

  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-lg transition-colors"
      style={{ ':hover': { background: 'rgba(255,255,255,0.02)' } }}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {posCfg && (
            <span
              className="text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wide shrink-0"
              style={{ background: posCfg.bg, color: posCfg.color }}
            >
              {posCfg.label}
            </span>
          )}
          <span className="text-sm font-medium text-body truncate">{who}</span>
        </div>
        <span className="text-xs text-muted">{market} · {overLabel}</span>
      </div>

      <div className="flex items-center gap-4 shrink-0">
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[9px] text-subtle">L5</span>
          <HitBar rate={l5} />
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[9px] text-subtle">L10</span>
          <HitBar rate={l10} />
        </div>
        {season != null && (
          <div className="flex flex-col items-end gap-0.5">
            <span className="text-[9px] text-subtle">Año</span>
            <HitBar rate={season} />
          </div>
        )}
      </div>

      <ReadBadge read={read} />
    </div>
  )
}
