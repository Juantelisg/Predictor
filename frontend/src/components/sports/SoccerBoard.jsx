import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { getSoccerToday } from '../../api/soccer'
import { useDate } from '../../hooks/useDate'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import styles from './SoccerBoard.module.css'

const pct = (x) => Math.round(x * 100) + '%'
const pctN = (x) => Math.round(x * 100)
const norm = (s) => String(s ?? '').trim().toLowerCase()
const confOf = (p) => (p >= 0.65 ? 'alta' : p >= 0.55 ? 'media' : 'baja')
const CONF_LABEL = { alta: 'ALTA', media: 'MEDIA', baja: 'MONEDA' }

function Flag({ url, code, size = 22 }) {
  return url
    ? <img className={styles.flag} style={{ width: size, height: size }} src={url} alt={code || ''} loading="lazy" />
    : <span className={styles.flagFallback} style={{ width: size, height: size }}>{(code || '??').slice(0, 3)}</span>
}

// Construye las filas de mercado de un partido (picks del modelo + mercados estándar),
// deduplicadas y ordenadas por probabilidad. Adjunta cuota/tier del edge cuando existe.
function marketRows(card) {
  const a = card.analysis || {}
  const edgeBy = Object.fromEntries((card.edge?.rows || []).map((r) => [norm(r.label), r]))
  const rows = []
  const seen = new Set()
  const add = (mkt, pick, prob, level, edgeKey, isPick) => {
    if (prob == null) return
    const key = norm(mkt + '|' + pick)
    if (seen.has(key)) return
    seen.add(key)
    const e = edgeKey != null ? edgeBy[norm(edgeKey)] : null
    rows.push({
      mkt, pick, prob,
      conf: level || confOf(prob),
      cuota: e?.odds ?? null,
      tier: e?.tier ?? null,
      isPick: !!isPick,
    })
  }
  ;(a.picks || []).forEach((p) => {
    const team = String(p.pick || '').replace(/^Gana\s+/i, '').trim()
    add(p.market, p.pick, p.prob, (p.level || '').toLowerCase() || null, team, true)
  })
  const fav = a.resultado?.length ? a.resultado.reduce((m, r) => (r.cal > m.cal ? r : m)) : null
  if (fav) {
    const favTeam = String(fav.label).replace(/^Gana\s+/i, '').trim()   // "Gana Brazil" -> "Brazil" (match edge)
    add('Resultado', fav.label, fav.cal, null, favTeam, false)
  }
  if (a.goles) {
    add('Goles', 'Over 1.5', a.goles.over15, null, null, false)
    add('Goles', 'Over 2.5', a.goles.over25, null, null, false)
    add('BTTS', 'Ambos marcan', a.goles.btts, null, null, false)
  }
  return rows.sort((x, y) => y.prob - x.prob)
}

function Badge({ conf }) {
  const cls = conf === 'alta' ? styles.bAlta : conf === 'media' ? styles.bMedia : styles.bBaja
  return <span className={`${styles.badge} ${cls}`}>{CONF_LABEL[conf] || conf.toUpperCase()}</span>
}

function meterColor(conf) {
  return conf === 'alta' ? 'var(--green)' : conf === 'media' ? 'var(--amber)' : 'var(--faint)'
}

function Group({ card, rows, active, onSelect }) {
  const best = rows[0]
  return (
    <div className={`${styles.group} ${active ? styles.sel : ''}`}>
      <button className={styles.gHead} onClick={onSelect} aria-label={`${card.home} vs ${card.away}`}>
        <span className={styles.gDot} />
        <span className={styles.gTime}>{card.time || '--:--'}</span>
        <span className={styles.gMatch}>
          <span className={styles.duo}>
            <Flag url={card.home_flag} code={card.home_code} size={20} />
            <span className={styles.flagB}><Flag url={card.away_flag} code={card.away_code} size={20} /></span>
          </span>
          <span className={styles.mm}>{card.home} vs {card.away}</span>
          {card.tag && <span className={styles.gRound}>{card.tag}</span>}
        </span>
        {best && <span className={styles.gSum}>mejor <b>{best.pick.replace(/^Gana\s+/i, '')} {pctN(best.prob)}%</b></span>}
        <span className={styles.chev}>▸</span>
      </button>
      <div className={styles.gBody}>
        {rows.map((r, i) => (
          <button key={i} className={`${styles.mRow} ${r.isPick ? styles.isPick : ''}`} onClick={onSelect}>
            <span className={styles.mMkt}>{r.mkt}</span>
            <span className={styles.mPick}>{r.pick}</span>
            <span className={`${styles.mProb} ${r.conf === 'alta' ? styles.pAlta : styles.pMedia}`}>{pctN(r.prob)}</span>
            <span className={styles.mConf}><Badge conf={r.conf} /></span>
            <span className={styles.mCuota}>{r.cuota != null ? Number(r.cuota).toFixed(2) : '—'}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function Detail({ card, rows }) {
  const [tab, setTab] = useState('mkt')
  const a = card.analysis || {}
  const res = a.resultado || []
  const favCal = res.length ? Math.max(...res.map((r) => r.cal)) : -1
  const edgeBy = Object.fromEntries((card.edge?.rows || []).map((r) => [norm(r.label), r]))
  const picks = rows.filter((r) => r.isPick)
  const others = rows.filter((r) => !r.isPick)

  const stats = [
    a.resultado?.length && ['Favorito', `${res.reduce((m, r) => (r.cal > m.cal ? r : m)).label} ${pctN(favCal)}%`],
    a.goles && ['Over 2.5', pct(a.goles.over25)],
    a.goles && ['Ambos marcan', pct(a.goles.btts)],
    a.corners && ['Córners esp.', String(a.corners.exp)],
  ].filter(Boolean)

  const Market = ({ r }) => (
    <div className={`${styles.mkt} ${r.isPick ? styles.pickRow : ''}`}>
      <div className={styles.mktH}>
        <span className={styles.mktNm}>{r.isPick && '★ '}{r.mkt} · {r.pick}</span>
        {r.cuota != null && <span className={styles.mktCu}>{Number(r.cuota).toFixed(2)}</span>}
        <Badge conf={r.conf} />
        <span className={styles.pin} style={{ color: r.conf === 'alta' ? 'var(--green)' : 'var(--txt)' }}>{pctN(r.prob)}%</span>
      </div>
      <div className={styles.meter}><i style={{ width: pct(r.prob), background: meterColor(r.conf) }} /></div>
    </div>
  )

  return (
    <section className={styles.detail}>
      <div className={styles.dTop}>Mundial 2026 · {card.tag || 'Fase actual'}<span className={styles.ic}>↗ ⤢ ⋯</span></div>

      <div className={styles.hero}>
        <div className={styles.matchup}>
          <div className={styles.side}>
            <Flag url={card.home_flag} code={card.home_code} size={54} />
            <div className={styles.nm}>{card.home}</div>
          </div>
          <div className={styles.mid}>
            {card.tag && <div className={styles.rd}>{card.tag}</div>}
            <div className={styles.ko}>{card.time || '--:--'}</div>
            <div className={styles.dt}>hora argentina</div>
          </div>
          <div className={styles.side}>
            <Flag url={card.away_flag} code={card.away_code} size={54} />
            <div className={styles.nm}>{card.away}</div>
          </div>
        </div>

        {res.length > 0 && (
          <div className={styles.bts}>
            {res.map((r, i) => {
              const win = r.cal === favCal
              const label = String(r.label).replace(/^Gana\s+/i, '')
              const e = edgeBy[norm(label)]
              return (
                <div key={i} className={`${styles.bt} ${win ? styles.win : ''}`}>
                  <span className={styles.lab}>{win && '★ '}{label}</span>
                  <span className={styles.pr}>{pctN(r.cal)}%</span>
                  {e?.odds != null && <span className={styles.cu}>{Number(e.odds).toFixed(2)}</span>}
                </div>
              )
            })}
          </div>
        )}

        {stats.length > 0 && (
          <div className={styles.stats}>
            {stats.map(([k, v], i) => (
              <div key={i} className={styles.stat}><div className={styles.k}>{k}</div><div className={styles.v}>{v}</div></div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'mkt' ? styles.on : ''}`} onClick={() => setTab('mkt')}>Mercados</button>
        <button className={`${styles.tab} ${tab === 'ctx' ? styles.on : ''}`} onClick={() => setTab('ctx')}>Lectura</button>
      </div>

      <div className={styles.dBody}>
        {tab === 'mkt' && (
          <>
            {picks.length > 0 && <div className={styles.secT}>Picks del modelo</div>}
            {picks.map((r, i) => <Market key={'p' + i} r={r} />)}
            {others.length > 0 && <div className={styles.secT}>Otros mercados</div>}
            {others.map((r, i) => <Market key={'o' + i} r={r} />)}
          </>
        )}
        {tab === 'ctx' && (
          card.lectura?.summary ? (
            <>
              <p className={styles.lead}>{card.lectura.summary}</p>
              {card.lectura.context?.length > 0 && <div className={styles.secT}>Contexto</div>}
              <ul className={styles.ctx}>
                {card.lectura.context?.map((x, i) => <li key={i}>{x}</li>)}
              </ul>
              {card.lectura.sources?.length > 0 && (
                <div className={styles.src}>
                  {card.lectura.sources.map((s, i) => (
                    <a key={i} href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
                  ))}
                </div>
              )}
            </>
          ) : <Empty title="Sin lectura en vivo" subtitle="Todavía no se generó el contexto de este partido." />
        )}
      </div>
    </section>
  )
}

export default function SoccerBoard() {
  const date = useDate()
  const [sel, setSel] = useState(0)
  const { data, isLoading, error } = useQuery({
    queryKey: ['soccer-today', date],
    queryFn: () => getSoccerToday(date),
    staleTime: 5 * 60_000,
  })

  const cards = data?.cards ?? []
  const allRows = useMemo(() => cards.map(marketRows), [cards])

  if (isLoading) return <div className={styles.pad}><Skeleton rows={6} /></div>
  if (error) return <Empty title="Error cargando partidos" subtitle={error.message} />
  if (!cards.length) return <Empty title="Sin partidos de fútbol hoy" subtitle={data?.note} />

  const cur = Math.min(sel, cards.length - 1)

  return (
    <div className={styles.board}>
      <div className={styles.list}>
        <div className={styles.listHead}>
          <div className={styles.brand}>
            <span className={styles.dot}>S</span>
            <b>Supra · Mundial 2026</b>
            <span className={styles.tag}>{cards.length} partidos</span>
          </div>
        </div>
        <div className={`${styles.colStrip} ${styles.up}`}>
          <span className={styles.l}>Mercado</span><span className={styles.l}>Pick</span>
          <span>Prob</span><span>Conf</span><span>Cuota</span>
        </div>
        <div className={styles.rows}>
          {cards.map((c, i) => (
            <Group key={i} card={c} rows={allRows[i]} active={i === cur} onSelect={() => setSel(i)} />
          ))}
        </div>
      </div>
      <Detail card={cards[cur]} rows={allRows[cur]} />
    </div>
  )
}
