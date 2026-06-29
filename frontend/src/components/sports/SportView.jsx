import { useSport } from '../../hooks/useSport'
import MatchPicker from '../match/MatchPicker'
import MatchWorkspace from '../match/MatchWorkspace'
import TrackRecord from './TrackRecord'
import OffSeason from './OffSeason'
import styles from './SportView.module.css'

const OFF_SEASON = ['nfl', 'nba']

export default function SportView() {
  const { sport, selectedMatch, clearMatch } = useSport()

  // NFL/NBA off-season: no workspace disponible
  if (OFF_SEASON.includes(sport)) {
    return (
      <main className={styles.main}>
        <OffSeason sport={sport} />
      </main>
    )
  }

  return (
    <main className={styles.main}>
      {selectedMatch ? (
        // Nivel 3: workspace del partido seleccionado
        <MatchWorkspace />
      ) : (
        // Nivel 1 + 2: picker de partidos
        <MatchPicker sport={sport} />
      )}
    </main>
  )
}
