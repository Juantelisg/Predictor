import { useQuery } from '@tanstack/react-query'
import { getMLBToday } from '../../api/mlb'
import { useDate } from '../../hooks/useDate'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import Pill from '../common/Pill'
import styles from './MLBToday.module.css'

const pct = (x) => Math.round(x * 100) + '%'

function GameCard({ g }) {
  return (
    <div className={styles.card} style={{ '--cat': g.cat }}>
      <div className={styles.head}>
        <span className={styles.rank}>#{g.rank}</span>
        <div className={styles.main}>
          <div className={styles.match}>
            {g.home}
            <span className={styles.vs}>vs</span>
            {g.away}
            <span className={styles.tag}>{g.tag}</span>
          </div>
        </div>
        <Pill label={`${g.hprob}%`} variant={g.hlevel?.toLowerCase()} />
      </div>
      <div className={styles.logros}>
        {(g.logros ?? []).map((l, i) => (
          <div key={i} className={styles.logro}>
            <span className={styles.lmkt}>{l.market}</span>
            <span className={styles.lpick}>{l.pick}</span>
            <Pill label={`${l.prob}%`} variant={l.level?.toLowerCase()} />
          </div>
        ))}
      </div>
      {g.analisis?.length > 0 && (
        <ul className={styles.notes}>
          {g.analisis.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      )}
    </div>
  )
}

export default function MLBToday() {
  const date = useDate()
  const { data, isLoading, error } = useQuery({
    queryKey: ['mlb-today', date],
    queryFn: () => getMLBToday(date),
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <Skeleton rows={4} />
  if (error) return <Empty title="Error cargando MLB" subtitle={error.message} />

  const cards = data?.cards ?? []
  if (!cards.length)
    return <Empty title="Sin partidos MLB hoy" subtitle={data?.note} />

  return (
    <div>
      {data.note && <p className={styles.note}>{data.note}</p>}
      <div className={styles.list}>
        {cards.map((c, i) => <GameCard key={i} g={c} />)}
      </div>
    </div>
  )
}
