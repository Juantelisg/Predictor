import { useSport } from '../../hooks/useSport'

function Flag({ url, code }) {
  if (url) return <img className="w-5 h-5 rounded-sm object-cover shrink-0" src={url} alt={code} loading="lazy" />
  return (
    <span className="w-5 h-5 rounded-sm bg-surface-3 flex items-center justify-center text-[9px] text-muted font-mono shrink-0">
      {code?.slice(0, 3) ?? '?'}
    </span>
  )
}

function QuickProb({ analysis }) {
  if (!analysis?.resultado?.length) return null
  return (
    <div className="flex gap-5 mt-3">
      {analysis.resultado.map((r, i) => {
        const p = Math.round((r.cal ?? r.prob) * 100)
        return (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <span className="text-[10px] text-subtle">{r.label?.split(' ')[0]}</span>
            <span className={`text-sm font-bold tabular ${p >= 65 ? 'text-accent' : p >= 50 ? 'text-body' : 'text-muted'}`}>
              {p}%
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function MatchCard({ card, compact = false }) {
  const { selectMatch, selectedMatch } = useSport()
  const picks = card.analysis?.picks ?? []
  const hasPicks = picks.length > 0
  const isSelected = selectedMatch?.home === card.home && selectedMatch?.away === card.away

  if (compact) {
    return (
      <button
        onClick={() => selectMatch(card)}
        className={`w-full text-left px-4 py-3 transition-colors ${
          isSelected
            ? 'border-l-2 border-accent bg-accent/[0.06]'
            : 'border-l-2 border-transparent hover:bg-white/[0.03]'
        } border-b border-white/[0.04]`}
      >
        <div className="flex items-center gap-2 mb-1">
          <Flag url={card.home_flag} code={card.home_code} />
          <span className="text-xs text-body truncate flex-1">{card.home}</span>
          {hasPicks && <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />}
        </div>
        <div className="flex items-center gap-2">
          <Flag url={card.away_flag} code={card.away_code} />
          <span className="text-xs text-muted truncate flex-1">{card.away}</span>
          {card.time && <span className="text-[10px] text-subtle tabular shrink-0">{card.time}</span>}
        </div>
      </button>
    )
  }

  return (
    <button
      onClick={() => selectMatch(card)}
      className="group relative w-full text-left p-4 rounded-xl border border-white/[0.07] bg-surface hover:border-white/[0.14] hover:bg-surface-2 transition-all duration-150"
    >
      <div className="flex items-center gap-2 mb-3">
        {card.time && <span className="text-[11px] text-muted tabular">{card.time}</span>}
        <div className="flex-1" />
        {hasPicks && (
          <span className="text-[11px] px-2 py-0.5 rounded-full border font-medium"
            style={{ background: 'rgba(94,234,212,0.1)', color: '#5eead4', borderColor: 'rgba(94,234,212,0.2)' }}>
            ✓ Picks
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Flag url={card.home_flag} code={card.home_code} />
          <span className="text-sm font-semibold text-body truncate">{card.home}</span>
        </div>
        <span className="text-xs text-subtle shrink-0 px-1">vs</span>
        <div className="flex items-center gap-2 flex-1 min-w-0 justify-end">
          <span className="text-sm font-semibold text-body truncate text-right">{card.away}</span>
          <Flag url={card.away_flag} code={card.away_code} />
        </div>
      </div>

      <QuickProb analysis={card.analysis} />

      {hasPicks && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {picks.slice(0, 2).map((p, i) => (
            <span key={i} className="text-[11px] px-2 py-0.5 rounded-md bg-surface-3 text-muted border border-white/[0.06]">
              {p.pick}
            </span>
          ))}
        </div>
      )}

      <span className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
        style={{ boxShadow: 'inset 0 0 0 1px rgba(94,234,212,0.1)' }} />
    </button>
  )
}
