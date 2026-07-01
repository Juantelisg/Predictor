import { useQuery } from '@tanstack/react-query'
import { getSoccerToday } from '../../api/soccer'
import { getMLBToday } from '../../api/mlb'
import { useDate } from '../../hooks/useDate'
import MatchCard from './MatchCard'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import OffSeason from '../sports/OffSeason'

function SoccerPicker({ date, compact }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['soccer-today', date],
    queryFn: () => getSoccerToday(date),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <Skeleton rows={compact ? 6 : 4} />
  if (error) return <Empty title="Error cargando partidos" subtitle={error.message} />
  const cards = data?.cards ?? []
  if (!cards.length) return <Empty title="Sin partidos de fútbol hoy" subtitle={data?.note} />

  if (compact) {
    return (
      <div>
        <p className="px-4 py-2.5 text-[10px] text-subtle uppercase tracking-widest font-semibold border-b border-white/[0.04]">
          {cards.length} partidos
        </p>
        {cards.map((c, i) => <MatchCard key={i} card={c} compact />)}
      </div>
    )
  }

  return (
    <>
      {data.note && <p className="text-xs text-muted mb-4">{data.note}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cards.map((c, i) => <MatchCard key={i} card={c} />)}
      </div>
    </>
  )
}

function MLBPicker({ date, compact }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['mlb-today', date],
    queryFn: () => getMLBToday(date),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <Skeleton rows={compact ? 6 : 4} />
  if (error) return <Empty title="Error cargando MLB" subtitle={error.message} />
  const cards = (data?.cards ?? []).map(c => ({
    home: c.home, away: c.away,
    home_flag: null, home_code: null,
    away_flag: null, away_code: null,
    time: null, cat: c.cat,
    analysis: {
      resultado: c.logros?.map(l => ({ label: l.market, prob: l.prob / 100, cal: l.prob / 100 })) ?? [],
      picks: c.logros?.map(l => ({ market: l.market, pick: l.pick, prob: l.prob / 100, level: l.level })) ?? [],
    },
    _mlbRaw: c,
  }))
  if (!cards.length) return <Empty title="Sin partidos MLB hoy" subtitle={data?.note} />

  if (compact) {
    return (
      <div>
        <p className="px-4 py-2.5 text-[10px] text-subtle uppercase tracking-widest font-semibold border-b border-white/[0.04]">
          {cards.length} partidos
        </p>
        {cards.map((c, i) => <MatchCard key={i} card={c} compact />)}
      </div>
    )
  }

  return (
    <>
      {data.note && <p className="text-xs text-muted mb-4">{data.note}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cards.map((c, i) => <MatchCard key={i} card={c} />)}
      </div>
    </>
  )
}

export default function MatchPicker({ sport, compact = false }) {
  const date = useDate()
  if (sport === 'nfl') return <OffSeason sport="nfl" />
  if (sport === 'nba') return <OffSeason sport="nba" />
  if (sport === 'mlb') return <MLBPicker date={date} compact={compact} />
  return <SoccerPicker date={date} compact={compact} />
}
