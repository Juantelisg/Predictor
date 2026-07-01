import { useQuery } from '@tanstack/react-query'
import { getBudget } from '../../api/ticket'
import { useSport } from '../../hooks/useSport'
import { useDate } from '../../hooks/useDate'

const SPORTS = [
  { id: 'soccer', label: 'Soccer', emoji: '⚽' },
  { id: 'mlb',    label: 'MLB',    emoji: '⚾' },
  { id: 'nfl',    label: 'NFL',    emoji: '🏈' },
  { id: 'nba',    label: 'NBA',    emoji: '🏀' },
]

export default function Header() {
  const { sport, setSport } = useSport()
  const date = useDate()
  const { data: budget } = useQuery({
    queryKey: ['budget'],
    queryFn: getBudget,
    staleTime: 60_000,
  })

  return (
    <header className="shrink-0 border-b border-white/[0.06] backdrop-blur-md bg-night/80">
      <div className="flex items-center gap-3 px-6 h-14">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent" style={{ boxShadow: '0 0 8px rgba(94,234,212,0.7)' }} />
          <span className="font-semibold tracking-tight text-body">predictor</span>
          <span className="text-muted text-xs">/</span>
          <span className="text-muted text-xs">análisis</span>
        </div>

        <div className="flex-1" />

        <span className="text-xs px-2.5 py-1 rounded-md bg-surface-2 text-muted tabular">
          {date}
        </span>

        {budget && (
          <span className="text-xs px-2.5 py-1 rounded-md bg-surface-2 text-muted tabular">
            API <span className="text-body font-medium">{budget.remaining}</span>/{budget.limit}
          </span>
        )}
      </div>

      <nav className="flex gap-1 px-6 pb-3">
        {SPORTS.map(s => (
          <button
            key={s.id}
            onClick={() => setSport(s.id)}
            className={`relative px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-150 ${
              sport === s.id
                ? 'text-accent border border-accent/30'
                : 'text-muted hover:text-body border border-transparent hover:bg-white/[0.04]'
            }`}
            style={sport === s.id ? { background: 'rgba(94,234,212,0.1)' } : {}}
          >
            {s.emoji} {s.label}
          </button>
        ))}
      </nav>
    </header>
  )
}
