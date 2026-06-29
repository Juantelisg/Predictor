import { useSport } from '../../hooks/useSport'
import TeamTab from './TeamTab'
import PlayersTab from './PlayersTab'
import styles from './MatchWorkspace.module.css'

export default function MatchWorkspace() {
  const { selectedMatch: match, activeMainTab, setMainTab, clearMatch } = useSport()
  if (!match) return null

  const hasPlayers =
    (match.analysis?.panorama?.length ?? 0) > 0 ||
    (match.analysis?.linemate?.length  ?? 0) > 0

  return (
    <div>
      {/* Header del partido */}
      <div className={styles.header}>
        <button className={styles.back} onClick={clearMatch}>
          ← Partidos
        </button>
        <div className={styles.matchTitle}>
          {match.home_flag && (
            <img className={styles.flag} src={match.home_flag} alt="" />
          )}
          <span className={styles.home}>{match.home}</span>
          <span className={styles.vs}>vs</span>
          <span className={styles.away}>{match.away}</span>
          {match.away_flag && (
            <img className={styles.flag} src={match.away_flag} alt="" />
          )}
        </div>
        {match.time && (
          <span className={styles.time}>{match.time}</span>
        )}
      </div>

      {/* Tabs principales: TEAM | PLAYERS */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeMainTab === 'team' ? styles.active : ''}`}
          onClick={() => setMainTab('team')}
        >
          TEAM
        </button>
        <button
          className={`${styles.tab} ${activeMainTab === 'players' ? styles.active : ''}`}
          onClick={() => setMainTab('players')}
        >
          PLAYERS
          {!hasPlayers && <span className={styles.noData}>sin datos</span>}
        </button>
      </div>

      {/* Contenido */}
      <div className={styles.body}>
        {activeMainTab === 'team'
          ? <TeamTab    match={match} />
          : <PlayersTab match={match} />
        }
      </div>
    </div>
  )
}
