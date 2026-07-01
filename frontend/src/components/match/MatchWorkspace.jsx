import { useSport } from '../../hooks/useSport'
import TeamTab from './TeamTab'
import PlayersTab from './PlayersTab'

export default function MatchWorkspace() {
  const { selectedMatch: match, activeMainTab, setMainTab, clearMatch } = useSport()
  if (!match) return null

  const hasPlayers =
    (match.analysis?.panorama?.length ?? 0) > 0 ||
    (match.analysis?.linemate?.length  ?? 0) > 0

  return (
    <div className="h-full flex flex-col">
      {/* Match header */}
      <div className="px-6 pt-5 pb-4 border-b border-white/[0.06] shrink-0">
        <button
          onClick={clearMatch}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-body mb-4 transition-colors"
        >
          ← Todos los partidos
        </button>

        <div className="flex items-center gap-3">
          {match.home_flag && (
            <img className="w-8 h-8 rounded object-cover" src={match.home_flag} alt="" />
          )}
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-body leading-snug">
              {match.home}
              <span className="text-muted font-normal mx-2 text-sm">vs</span>
              {match.away}
            </h2>
            {match.time && (
              <span className="text-xs text-muted tabular">{match.time}</span>
            )}
          </div>
          {match.away_flag && (
            <img className="w-8 h-8 rounded object-cover" src={match.away_flag} alt="" />
          )}
        </div>
      </div>

      {/* Main tabs */}
      <div className="flex gap-0 px-6 shrink-0 border-b border-white/[0.06]">
        {['team', 'players'].map(tab => (
          <button
            key={tab}
            onClick={() => setMainTab(tab)}
            className={`px-4 py-3 text-xs font-semibold uppercase tracking-widest transition-colors border-b-2 ${
              activeMainTab === tab
                ? 'text-accent border-accent'
                : 'text-muted hover:text-body border-transparent'
            }`}
          >
            {tab}
            {tab === 'players' && !hasPlayers && (
              <span className="ml-1.5 text-[10px] text-subtle normal-case tracking-normal opacity-60">sin datos</span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {activeMainTab === 'team'
          ? <TeamTab match={match} />
          : <PlayersTab match={match} />
        }
      </div>
    </div>
  )
}
