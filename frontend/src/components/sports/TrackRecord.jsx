import { useQuery } from '@tanstack/react-query'
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip,
  ReferenceLine, ResponsiveContainer,
  BarChart, Bar, Cell,
} from 'recharts'
import { getTrackRecord, getSoccerHistory } from '../../api/soccer'
import Skeleton from '../common/Skeleton'
import Empty from '../common/Empty'
import styles from './TrackRecord.module.css'

function StatBox({ value, label }) {
  return (
    <div className={styles.statBox}>
      <div className={styles.statVal}>{value ?? '—'}</div>
      <div className={styles.statLab}>{label}</div>
    </div>
  )
}

function GameRow({ g }) {
  return (
    <div className={styles.game}>
      <div className={styles.gameHead}>
        <span className={styles.gameMatch}>{g.home} vs {g.away}</span>
        <span className={styles.gameDate}>{g.date}</span>
        {g.result && <span className={styles.gameRes}>{g.result}</span>}
      </div>
      {(g.picks ?? []).map((p, i) => (
        <div key={i} className={styles.pick}>
          <span className={`${styles.pickOut} ${p.outcome ? styles.win : styles.loss}`}>
            {p.outcome ? '✓' : '✗'}
          </span>
          <span className={styles.pickLab}>{p.label}</span>
          <span className={styles.pickProb}>{Math.round(p.prob * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

export default function TrackRecord() {
  const { data: tr, isLoading: l1 } = useQuery({
    queryKey: ['track-record'],
    queryFn: () => getTrackRecord(),
    staleTime: 30 * 60_000,
  })
  const { data: hist, isLoading: l2 } = useQuery({
    queryKey: ['history', 14],
    queryFn: () => getSoccerHistory(14),
    staleTime: 30 * 60_000,
  })

  if (l1 || l2) return <Skeleton rows={5} />

  const calib  = tr?.calibration ?? {}
  const byMkt  = tr?.by_market   ?? {}
  const roi    = tr?.roi         ?? {}
  const games  = (hist?.games ?? []).slice(0, 20)

  const brier = calib.brier != null ? calib.brier.toFixed(4) : null
  const ece   = calib.ece   != null ? calib.ece.toFixed(4)   : null
  const acc   = calib.acc   != null ? (calib.acc * 100).toFixed(1) + '%' : null

  const buckets = (calib.buckets ?? [])
    .filter(b => b.n > 0)
    .map(b => ({
      x: Math.round(b.avg_prob * 1000) / 10,
      y: Math.round(b.actual_rate * 1000) / 10,
      n: b.n,
    }))

  const tiers = Object.entries(roi.tiers ?? {}).map(([k, v]) => ({
    name: k, pnl: v.pnl_flat,
  }))

  return (
    <div className={styles.wrap}>
      <div className={styles.statsRow}>
        <StatBox value={brier} label="Brier Score" />
        <StatBox value={ece}   label="ECE" />
        <StatBox value={acc}   label="Accuracy" />
        <StatBox value={calib.n ?? 0} label="Predicciones" />
      </div>

      {buckets.length > 0 && (
        <div className={styles.chartBox}>
          <h4 className={styles.chartTitle}>
            Reliability Diagram · predicha vs real por decil
          </h4>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
              <XAxis
                dataKey="x" type="number" domain={[0, 100]} name="Predicha (%)"
                label={{ value: 'Prob. predicha (%)', position: 'insideBottom', offset: -10, fill: 'var(--faint)', fontSize: 11 }}
                tick={{ fill: 'var(--faint)', fontSize: 11 }}
              />
              <YAxis
                dataKey="y" type="number" domain={[0, 100]} name="Real (%)"
                label={{ value: 'Tasa real (%)', angle: -90, position: 'insideLeft', fill: 'var(--faint)', fontSize: 11 }}
                tick={{ fill: 'var(--faint)', fontSize: 11 }}
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3', stroke: 'var(--line)' }}
                contentStyle={{ background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }}
                formatter={(v, name, props) => [`${v}% (n=${props.payload.n})`, name]}
              />
              <ReferenceLine
                segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]}
                stroke="rgba(255,255,255,0.15)" strokeDasharray="5 4"
              />
              <Scatter data={buckets} fill="var(--accent)" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      {Object.keys(byMkt).length > 0 && (
        <div className={styles.chartBox}>
          <h4 className={styles.chartTitle}>Por mercado</h4>
          <table className={styles.mktTable}>
            <thead>
              <tr>
                <th>Mercado</th><th>N</th><th>Brier</th><th>Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byMkt).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{v.n}</td>
                  <td>{v.brier.toFixed(4)}</td>
                  <td>{(v.acc * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tiers.length > 0 && (
        <div className={styles.chartBox}>
          <h4 className={styles.chartTitle}>
            PnL por tier · {roi.total?.n ?? 0} apuestas rastreadas
          </h4>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={tiers} margin={{ top: 10, right: 20, bottom: 5, left: 0 }}>
              <XAxis dataKey="name" tick={{ fill: 'var(--faint)', fontSize: 11 }} />
              <YAxis tick={{ fill: 'var(--faint)', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }}
              />
              <Bar dataKey="pnl" radius={[5, 5, 0, 0]}>
                {tiers.map((t, i) => (
                  <Cell key={i} fill={t.pnl >= 0 ? 'rgba(94,234,212,.65)' : 'rgba(248,113,113,.55)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className={styles.histSection}>
        <h4 className={styles.chartTitle}>Últimos {games.length} partidos evaluados</h4>
        {games.length
          ? games.map((g, i) => <GameRow key={i} g={g} />)
          : <Empty title="Sin resultados evaluados aún" subtitle="Los resultados aparecen aquí después de que cierra cada partido." />
        }
      </div>
    </div>
  )
}
