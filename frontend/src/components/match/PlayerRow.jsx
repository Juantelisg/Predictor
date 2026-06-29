import styles from './PlayerRow.module.css'

function HitBar({ rate }) {
  if (rate == null) return <span className={styles.nodata}>—</span>
  const w = Math.min(100, Math.max(0, rate))
  const cls = rate >= 80 ? styles.barHot : rate >= 60 ? styles.barWarm : rate >= 40 ? styles.barMid : styles.barCold
  return (
    <div className={styles.barWrap}>
      <div className={`${styles.bar} ${cls}`} style={{ width: w + '%' }} />
      <span className={styles.barLabel}>{rate}%</span>
    </div>
  )
}

function ReadBadge({ read }) {
  if (!read) return null
  const cls = read.includes('alto') ? styles.hot
    : read.includes('buena') ? styles.warm
    : read.includes('bajo') ? styles.cold
    : styles.mid
  return <span className={`${styles.readBadge} ${cls}`}>{read}</span>
}

export default function PlayerRow({ player }) {
  const { who, market, side, line, l5, l10, season, read } = player
  const overLabel = side === 'over' ? `Over ${line}` : side === 'under' ? `Under ${line}` : String(line ?? '')

  return (
    <div className={styles.row}>
      <div className={styles.left}>
        <span className={styles.name}>{who}</span>
        <span className={styles.market}>{market} · {overLabel}</span>
      </div>

      <div className={styles.stats}>
        <div className={styles.statCol}>
          <span className={styles.statLab}>L5</span>
          <HitBar rate={l5} />
        </div>
        <div className={styles.statCol}>
          <span className={styles.statLab}>L10</span>
          <HitBar rate={l10} />
        </div>
        {season != null && (
          <div className={styles.statCol}>
            <span className={styles.statLab}>Año</span>
            <HitBar rate={season} />
          </div>
        )}
      </div>

      <ReadBadge read={read} />
    </div>
  )
}
