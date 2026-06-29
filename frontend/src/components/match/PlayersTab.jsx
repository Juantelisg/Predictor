import { useSport } from '../../hooks/useSport'
import PlayerRow from './PlayerRow'
import Empty from '../common/Empty'
import styles from './PlayersTab.module.css'

function normalize(code) { return (code ?? '').toUpperCase().trim() }

export default function PlayersTab({ match }) {
  const { activeSubTeam, setSubTeam, activeCategory, setCategory } = useSport()

  const panorama = match.analysis?.panorama ?? []
  const linemate  = match.analysis?.linemate  ?? []

  // Unificar fuentes: panorama y linemate tienen esquemas similares
  const allPlayers = [
    ...panorama.map(p => ({ ...p, _src: 'panorama' })),
    ...linemate.map(p => ({
      who: p.who, market: p.market, side: p.over != null ? 'over' : null,
      line: p.line, l5: p.l5, l10: p.l10, season: p.season,
      team: p.team, read: p.read, _src: 'linemate',
    })),
  ]

  // Inferir teams de los jugadores vs los códigos del partido
  const homeCode = normalize(match.home_code ?? match.home)
  const awayCode = normalize(match.away_code ?? match.away)

  const teamPlayers = allPlayers.filter(p => {
    const t = normalize(p.team)
    if (activeSubTeam === 'home') {
      return t === homeCode || t === normalize(match.home)
    } else {
      return t === awayCode || t === normalize(match.away)
    }
  })

  // Si no hay team info en los jugadores, mostrar todos (fallback)
  const playersToShow = teamPlayers.length > 0 ? teamPlayers : allPlayers

  // Categorías únicas
  const categories = [...new Set(playersToShow.map(p => p.market).filter(Boolean))]

  const filtered = activeCategory
    ? playersToShow.filter(p => p.market === activeCategory)
    : playersToShow

  const teamLabel = (side) => side === 'home' ? match.home : match.away
  const flagFor   = (side) => side === 'home' ? match.home_flag : match.away_flag

  return (
    <div>
      {/* Selector Home | Away */}
      <div className={styles.teamSelector}>
        {['home', 'away'].map(side => (
          <button
            key={side}
            className={`${styles.teamBtn} ${activeSubTeam === side ? styles.active : ''}`}
            onClick={() => setSubTeam(side)}
          >
            {flagFor(side) && (
              <img className={styles.miniFlag} src={flagFor(side)} alt="" />
            )}
            {teamLabel(side)}
          </button>
        ))}
      </div>

      {/* Filtros de categoría */}
      {categories.length > 0 && (
        <div className={styles.cats}>
          <button
            className={`${styles.cat} ${!activeCategory ? styles.catActive : ''}`}
            onClick={() => setCategory(null)}
          >
            Todos
          </button>
          {categories.map(c => (
            <button
              key={c}
              className={`${styles.cat} ${activeCategory === c ? styles.catActive : ''}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Lista de jugadores */}
      {filtered.length > 0 ? (
        <div className={styles.list}>
          <div className={styles.listHeader}>
            <span className={styles.hName}>Jugador · Mercado</span>
            <span className={styles.hStats}>L5 · L10 · Año</span>
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
        <p className={styles.src}>
          Fuente: Linemate / panorama de rendimiento.
          Tasas históricas sin ajuste por contexto del partido.
        </p>
      )}
    </div>
  )
}
