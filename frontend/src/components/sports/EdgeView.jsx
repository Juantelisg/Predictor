import { useQuery } from '@tanstack/react-query'
import { getSoccerEdge } from '../../api/soccer'
import { useDate } from '../../hooks/useDate'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import styles from './EdgeView.module.css'

const TIER_META = {
  FUERTE:    { cls: 'fuerte', label: 'FUERTE' },
  MODERADO:  { cls: 'mod',    label: 'MOD' },
  BAJO:      { cls: 'bajo',   label: 'BAJO' },
  PASAR:     { cls: 'pass',   label: 'pass' },
  'NO-APTO': { cls: 'pass',   label: '—' },
  SOSPECHOSO:{ cls: 'susp',   label: 'SUSP' },
}

function MarketChip({ m }) {
  const hasEdge = m.tier !== 'PASAR' && m.tier !== 'NO-APTO'
  const meta = TIER_META[m.tier] || TIER_META.PASAR
  const eg = hasEdge
    ? (m.edge >= 0 ? '+' : '') + (Math.round(m.edge * 1000) / 10) + '%'
    : '—'

  return (
    <div className={`${styles.chip} ${hasEdge ? styles.chipActive : ''}`}>
      <span className={styles.chipName}>{m.label}</span>
      <span className={`${styles.chipVal} ${hasEdge ? styles.pos : styles.neutral}`}>{eg}</span>
      <span className={`${styles.chipTier} ${styles[meta.cls]}`}>{meta.label}</span>
    </div>
  )
}

function EdgeRow({ r }) {
  return (
    <div className={styles.row}>
      <div className={styles.match}>
        <span className={styles.time}>{r.time ?? ''}</span>
        <span className={styles.teams}>
          {r.home} <span className={styles.vs}>vs</span> {r.away}
        </span>
        <span className={styles.prov}>{r.provider ?? 'ESPN'}</span>
      </div>
      <div className={styles.chips}>
        {(r.markets ?? []).map((m, i) => <MarketChip key={i} m={m} />)}
      </div>
    </div>
  )
}

export default function EdgeView() {
  const date = useDate()
  const { data, isLoading, error } = useQuery({
    queryKey: ['edge-today', date],
    queryFn: () => getSoccerEdge(date),
    staleTime: 10 * 60_000,
  })

  if (isLoading) return <Skeleton rows={4} />
  if (error) return <Empty title="Error cargando edge" subtitle={error.message} />

  const rows = data?.rows ?? []
  if (!rows.length)
    return (
      <Empty
        title="Sin datos de edge hoy"
        subtitle="El edge se calcula cuando hay cuotas ESPN disponibles."
      />
    )

  return (
    <div>
      <p className={styles.note}>
        Edge = modelo calibrado vs cuota ESPN de-vigeada. Ordenado por mayor edge.
      </p>
      <div className={styles.list}>
        {rows.map((r, i) => <EdgeRow key={i} r={r} />)}
      </div>
      <p className={styles.warn}>
        SUSP = edge {'>'} 20% vs book líquido = probable error del modelo, no value real.
      </p>
    </div>
  )
}
