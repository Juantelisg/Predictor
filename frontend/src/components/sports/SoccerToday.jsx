import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { getSoccerToday } from '../../api/soccer'
import { useDate } from '../../hooks/useDate'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import Pill from '../common/Pill'
import styles from './SoccerToday.module.css'

const pct = (x) => Math.round(x * 100) + '%'
const esc = (s) => String(s ?? '')

function Flag({ url, code }) {
  return url
    ? <img className={styles.flag} src={url} alt={code} loading="lazy" />
    : <span className={styles.flagFallback}>{code?.slice(0, 2)}</span>
}

function MarketRow({ label, prob, cal }) {
  const lvl = prob >= 0.65 ? 'alta' : prob >= 0.55 ? 'media' : 'baja'
  return (
    <div className={styles.mrow}>
      <span className={styles.mlab}>{label}</span>
      {cal != null && <span className={styles.mcal}>cal {pct(cal)}</span>}
      <Pill label={pct(prob)} variant={lvl} />
    </div>
  )
}

function GameCard({ c }) {
  const [open, setOpen] = useState(false)
  const a = c.analysis
  const fav = a?.resultado?.reduce((m, r) => r.cal > m.cal ? r : m)
  const lvl = fav ? (fav.cal >= 0.65 ? 'alta' : fav.cal >= 0.55 ? 'media' : 'baja') : 'baja'

  return (
    <div className={`${styles.card} ${open ? styles.open : ''}`}
      style={{ '--cat': c.cat }}>
      <button className={styles.head} onClick={() => setOpen(!open)}>
        <span className={styles.time}>{c.time}</span>
        <div className={styles.teams}>
          <span className={styles.team}>
            <Flag url={c.home_flag} code={c.home_code} />
            {c.home}
          </span>
          <span className={styles.vs}>vs</span>
          <span className={styles.team}>
            <Flag url={c.away_flag} code={c.away_code} />
            {c.away}
          </span>
        </div>
        {fav
          ? <Pill label={pct(fav.cal)} variant={lvl} />
          : <span className={styles.nodata}>s/d</span>
        }
        <ChevronRight size={14} className={styles.chev} />
      </button>

      {open && a && (
        <div className={styles.body}>
          {a.picks?.length > 0 && (
            <section className={styles.sec}>
              <h4 className={styles.secTitle}>Picks confiables</h4>
              {a.picks.map((p, i) => (
                <div key={i} className={styles.pick}>
                  <span className={styles.pickMkt}>{p.market}</span>
                  <span className={styles.pickLab}>{p.pick}</span>
                  <Pill label={pct(p.prob)} variant={p.level?.toLowerCase()} />
                </div>
              ))}
            </section>
          )}

          <section className={styles.sec}>
            <h4 className={styles.secTitle}>Resultado 1X2</h4>
            {a.resultado.map((r, i) => (
              <MarketRow key={i} label={r.label} prob={r.prob} cal={r.cal} />
            ))}
          </section>

          <section className={styles.sec}>
            <h4 className={styles.secTitle}>Goles</h4>
            {[
              ['Over 1.5', a.goles.over15],
              ['Over 2.5', a.goles.over25],
              ['Over 3.5', a.goles.over35],
              ['Ambos marcan', a.goles.btts],
            ].map(([lab, p]) => <MarketRow key={lab} label={lab} prob={p} />)}
          </section>

          {a.corners && (
            <section className={styles.sec}>
              <h4 className={styles.secTitle}>Corners · esp. {a.corners.exp}</h4>
              {[
                ['Over 8.5', a.corners.o85],
                ['Over 9.5', a.corners.o95],
                ['Over 10.5', a.corners.o105],
              ].map(([lab, p]) => <MarketRow key={lab} label={lab} prob={p} />)}
            </section>
          )}

          {c.lectura?.summary && (
            <section className={styles.sec}>
              <h4 className={styles.secTitle}>Contexto en vivo</h4>
              <p className={styles.summary}>{c.lectura.summary}</p>
              {c.lectura.context?.map((x, i) => (
                <p key={i} className={styles.ctx}>{x}</p>
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  )
}

export default function SoccerToday() {
  const date = useDate()
  const { data, isLoading, error } = useQuery({
    queryKey: ['soccer-today', date],
    queryFn: () => getSoccerToday(date),
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <Skeleton rows={5} />
  if (error) return <Empty title="Error cargando partidos" subtitle={error.message} />

  const cards = data?.cards ?? []
  if (!cards.length)
    return <Empty title="Sin partidos de fútbol hoy" subtitle={data?.note} />

  return (
    <div>
      {data.note && <p className={styles.note}>{data.note}</p>}
      <div className={styles.list}>
        {cards.map((c, i) => <GameCard key={i} c={c} />)}
      </div>
    </div>
  )
}
