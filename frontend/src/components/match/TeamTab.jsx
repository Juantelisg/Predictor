import { useSport } from '../../hooks/useSport'
import Pill from '../common/Pill'
import styles from './TeamTab.module.css'

const pct = (x) => Math.round((x ?? 0) * 100) + '%'

const TIER_META = {
  FUERTE:    { cls: styles.fuerte, label: 'FUERTE' },
  MODERADO:  { cls: styles.mod,    label: 'MOD' },
  BAJO:      { cls: styles.bajo,   label: 'BAJO' },
  PASAR:     { cls: styles.pass,   label: 'pass' },
  'NO-APTO': { cls: styles.pass,   label: '—' },
  SOSPECHOSO:{ cls: styles.susp,   label: 'SUSP' },
}

function EdgeRow({ r }) {
  const meta = TIER_META[r.tier] ?? TIER_META.PASAR
  const hasEdge = r.tier !== 'PASAR' && r.tier !== 'NO-APTO'
  const eg = hasEdge
    ? (r.edge >= 0 ? '+' : '') + (Math.round(r.edge * 1000) / 10) + '%'
    : '—'
  return (
    <div className={styles.edgeRow}>
      <span className={styles.edgeLab}>{r.label}</span>
      <span className={styles.edgeMeta}>
        modelo {pct(r.p_model)} · mkt {pct(r.p_market)}
      </span>
      <span className={`${styles.edgeVal} ${hasEdge ? styles.pos : styles.neu}`}>{eg}</span>
      <span className={`${styles.edgeTier} ${meta.cls}`}>{meta.label}</span>
    </div>
  )
}

function MktRow({ label, prob, cal, pickLevel }) {
  const lvl = (cal ?? prob) >= 0.65 ? 'alta' : (cal ?? prob) >= 0.55 ? 'media' : 'baja'
  return (
    <div className={`${styles.mktRow} ${pickLevel ? styles.isPick : ''}`}>
      {pickLevel && <span className={styles.pickDot} />}
      <span className={styles.mktLab}>{label}</span>
      {cal != null && <span className={styles.mktCal}>cal {pct(cal)}</span>}
      <Pill label={pct(cal ?? prob)} variant={pickLevel?.toLowerCase() ?? lvl} />
    </div>
  )
}

// match pick label contra market label con tolerancia (ej: "Ambos marcan" vs "Ambos marcan (BTTS)")
function pickLevel(label, pickMap) {
  const exact = pickMap[label]
  if (exact) return exact
  for (const [k, v] of Object.entries(pickMap)) {
    if (label.startsWith(k) || k.startsWith(label)) return v
  }
  return null
}

function SoccerTeamContent({ match, side }) {
  const a = match.analysis
  const edge = match.edge
  if (!a) return <p className={styles.empty}>Sin análisis disponible.</p>

  // índice de picks: { "Local gana": "ALTA", "Over 2.5": "MEDIA", ... }
  const pickMap = Object.fromEntries((a.picks ?? []).map(p => [p.pick, p.level]))

  return (
    <div className={styles.content}>
      {edge?.rows?.length > 0 && (
        <section className={styles.sec}>
          <h4 className={styles.secTitle}>Edge vs mercado · {edge.provider}</h4>
          {edge.rows.map((r, i) => <EdgeRow key={i} r={r} />)}
          <p className={styles.warn}>
            SUSP = edge {'>'} 20%: probable error del modelo.
          </p>
        </section>
      )}

      <section className={styles.sec}>
        <h4 className={styles.secTitle}>Resultado 1X2</h4>
        {a.resultado?.map((r, i) => (
          <MktRow key={i} label={r.label} prob={r.prob} cal={r.cal}
            pickLevel={pickLevel(r.label, pickMap)} />
        ))}
      </section>

      <section className={styles.sec}>
        <h4 className={styles.secTitle}>Goles</h4>
        {[
          ['Over 1.5', a.goles?.over15],
          ['Over 2.5', a.goles?.over25],
          ['Over 3.5', a.goles?.over35],
          ['Ambos marcan (BTTS)', a.goles?.btts],
        ].filter(([, v]) => v != null).map(([lab, p]) => (
          <MktRow key={lab} label={lab} prob={p}
            pickLevel={pickLevel(lab, pickMap)} />
        ))}
      </section>

      {a.valla && (
        <section className={styles.sec}>
          <h4 className={styles.secTitle}>Valla invicta</h4>
          <MktRow label={match.home} prob={a.valla.home}
            pickLevel={pickLevel(match.home, pickMap)} />
          <MktRow label={match.away} prob={a.valla.away}
            pickLevel={pickLevel(match.away, pickMap)} />
        </section>
      )}

      {a.corners && (
        <section className={styles.sec}>
          <h4 className={styles.secTitle}>Corners · esp. {a.corners.exp}</h4>
          {[
            ['Over 8.5', a.corners.o85],
            ['Over 9.5', a.corners.o95],
            ['Over 10.5', a.corners.o105],
          ].map(([lab, p]) => (
            <MktRow key={lab} label={lab} prob={p}
              pickLevel={pickLevel(lab, pickMap)} />
          ))}
        </section>
      )}
    </div>
  )
}

function MLBTeamContent({ match, side }) {
  const raw = match._mlbRaw
  if (!raw) return <p className={styles.empty}>Sin datos del equipo.</p>
  return (
    <div className={styles.content}>
      <section className={styles.sec}>
        <h4 className={styles.secTitle}>Análisis</h4>
        {(raw.logros ?? []).map((l, i) => (
          <MktRow key={i} label={`${l.market}: ${l.pick}`} prob={l.prob / 100} />
        ))}
      </section>
      {(raw.analisis ?? []).length > 0 && (
        <section className={styles.sec}>
          <h4 className={styles.secTitle}>Contexto</h4>
          {raw.analisis.map((a, i) => (
            <p key={i} className={styles.note}>{a}</p>
          ))}
        </section>
      )}
    </div>
  )
}

export default function TeamTab({ match }) {
  const { activeSubTeam, setSubTeam } = useSport()
  const isSoccer = !match._mlbRaw

  return (
    <div>
      {/* Selector Home | Away */}
      <div className={styles.teamSelector}>
        <button
          className={`${styles.teamBtn} ${activeSubTeam === 'home' ? styles.active : ''}`}
          onClick={() => setSubTeam('home')}
        >
          {match.home_flag && (
            <img className={styles.miniFlag} src={match.home_flag} alt="" />
          )}
          {match.home}
        </button>
        <button
          className={`${styles.teamBtn} ${activeSubTeam === 'away' ? styles.active : ''}`}
          onClick={() => setSubTeam('away')}
        >
          {match.away_flag && (
            <img className={styles.miniFlag} src={match.away_flag} alt="" />
          )}
          {match.away}
        </button>
      </div>

      {isSoccer
        ? <SoccerTeamContent match={match} side={activeSubTeam} />
        : <MLBTeamContent    match={match} side={activeSubTeam} />
      }
    </div>
  )
}
