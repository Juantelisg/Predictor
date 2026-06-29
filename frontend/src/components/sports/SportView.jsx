import { useSport } from '../../hooks/useSport'
import SubNav from '../layout/SubNav'
import SoccerToday from './SoccerToday'
import EdgeView from './EdgeView'
import TrackRecord from './TrackRecord'
import MLBToday from './MLBToday'
import OffSeason from './OffSeason'
import styles from './SportView.module.css'

function SoccerRouter({ subtab }) {
  if (subtab === 'edge')   return <EdgeView />
  if (subtab === 'record') return <TrackRecord />
  return <SoccerToday />
}

function MLBRouter({ subtab }) {
  if (subtab === 'edge')   return <OffSeason sport="mlb" />
  if (subtab === 'record') return <TrackRecord />
  return <MLBToday />
}

export default function SportView() {
  const { sport, subtab } = useSport()

  return (
    <div>
      <SubNav />
      <main className={styles.main}>
        {sport === 'soccer' && <SoccerRouter subtab={subtab} />}
        {sport === 'mlb'    && <MLBRouter    subtab={subtab} />}
        {sport === 'nfl'    && <OffSeason    sport="nfl" />}
        {sport === 'nba'    && <OffSeason    sport="nba" />}
      </main>
    </div>
  )
}
