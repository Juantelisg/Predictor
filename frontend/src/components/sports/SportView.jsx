import { useSport } from '../../hooks/useSport'
import MatchPicker from '../match/MatchPicker'
import MatchWorkspace from '../match/MatchWorkspace'
import OffSeason from './OffSeason'
import SoccerBoard from './SoccerBoard'

const OFF_SEASON = ['nfl', 'nba']

export default function SportView() {
  const { sport, selectedMatch } = useSport()

  if (OFF_SEASON.includes(sport)) {
    return (
      <main className="flex-1 overflow-y-auto">
        <OffSeason sport={sport} />
      </main>
    )
  }

  // Fútbol: vista master-detail dedicada (listado de picks agrupado + detalle del partido).
  if (sport === 'soccer') {
    return (
      <main className="flex-1 overflow-hidden">
        <SoccerBoard />
      </main>
    )
  }

  return (
    <main className="flex-1 overflow-hidden flex">
      {selectedMatch ? (
        <>
          {/* Sidebar: compact match list */}
          <aside className="w-[300px] shrink-0 border-r border-white/[0.06] overflow-y-auto bg-surface/50">
            <MatchPicker sport={sport} compact />
          </aside>
          {/* Workspace */}
          <div className="flex-1 overflow-hidden flex flex-col">
            <MatchWorkspace />
          </div>
        </>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <MatchPicker sport={sport} />
        </div>
      )}
    </main>
  )
}
