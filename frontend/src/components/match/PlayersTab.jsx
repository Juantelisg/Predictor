import { useSport } from '../../hooks/useSport'
import PlayerRow from './PlayerRow'
import Empty from '../common/Empty'

function normalize(code) { return (code ?? '').toUpperCase().trim() }

export default function PlayersTab({ match }) {
  const { activeSubTeam, setSubTeam, activeCategory, setCategory } = useSport()

  const panorama = match.analysis?.panorama ?? []
  const linemate  = match.analysis?.linemate  ?? []

  const allPlayers = [
    ...panorama.map(p => ({ ...p, _src: 'panorama' })),
    ...linemate.map(p => ({
      who: p.who, market: p.market, side: p.over != null ? 'over' : null,
      line: p.line, l5: p.l5, l10: p.l10, season: p.season,
      team: p.team, read: p.read, _src: 'linemate',
    })),
  ]

  const homeCode = normalize(match.home_code ?? match.home)
  const awayCode = normalize(match.away_code ?? match.away)

  const teamPlayers = allPlayers.filter(p => {
    const t = normalize(p.team)
    return activeSubTeam === 'home'
      ? t === homeCode || t === normalize(match.home)
      : t === awayCode || t === normalize(match.away)
  })

  const playersToShow = teamPlayers.length > 0 ? teamPlayers : allPlayers
  const categories = [...new Set(playersToShow.map(p => p.market).filter(Boolean))]

  const filtered = activeCategory
    ? playersToShow.filter(p => p.market === activeCategory)
    : playersToShow

  return (
    <div>
      {/* Team selector */}
      <div className="flex gap-1 mb-4 p-1 rounded-xl inline-flex" style={{ background: 'rgba(20,27,39,0.8)' }}>
        {['home', 'away'].map(side => {
          const label = side === 'home' ? match.home : match.away
          const flag  = side === 'home' ? match.home_flag : match.away_flag
          return (
            <button
              key={side}
              onClick={() => setSubTeam(side)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeSubTeam === side ? 'text-body' : 'text-muted hover:text-body'
              }`}
              style={activeSubTeam === side ? { background: 'rgba(255,255,255,0.07)' } : {}}
            >
              {flag && <img className="w-4 h-4 rounded-sm object-cover" src={flag} alt="" />}
              <span className="truncate max-w-[110px]">{label}</span>
            </button>
          )
        })}
      </div>

      {/* Category filters */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          <button
            onClick={() => setCategory(null)}
            className="px-3 py-1 text-xs rounded-full border transition-colors"
            style={!activeCategory
              ? { background: 'rgba(94,234,212,0.1)', color: '#5eead4', borderColor: 'rgba(94,234,212,0.3)' }
              : { background: 'transparent', color: '#8892a4', borderColor: 'rgba(255,255,255,0.08)' }
            }
          >
            Todos
          </button>
          {categories.map(c => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className="px-3 py-1 text-xs rounded-full border transition-colors"
              style={activeCategory === c
                ? { background: 'rgba(94,234,212,0.1)', color: '#5eead4', borderColor: 'rgba(94,234,212,0.3)' }
                : { background: 'transparent', color: '#8892a4', borderColor: 'rgba(255,255,255,0.08)' }
              }
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Player list */}
      {filtered.length > 0 ? (
        <div>
          <div className="flex items-center gap-4 px-3 pb-2 border-b border-white/[0.06] mb-1">
            <span className="text-[10px] text-subtle uppercase tracking-wider flex-1">Jugador</span>
            <span className="text-[10px] text-subtle uppercase tracking-wider">Hits</span>
          </div>
          {filtered.map((p, i) => <PlayerRow key={i} player={p} />)}
        </div>
      ) : (
        <Empty
          title="Sin datos de jugadores"
          subtitle={
            allPlayers.length > 0
              ? `Hay ${allPlayers.length} jugadores pero ninguno clasificado para este equipo.`
              : 'No hay props de jugadores disponibles para este partido.'
          }
        />
      )}

      {allPlayers.length > 0 && (
        <p className="text-[11px] text-subtle mt-4 pt-3 border-t border-white/[0.04]">
          Fuente: Linemate / panorama. Tasas sin ajuste por contexto del partido.
        </p>
      )}
    </div>
  )
}
