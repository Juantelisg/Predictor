import { useSport } from '../../hooks/useSport'
import styles from './MatchCard.module.css'

function Flag({ url, code }) {
  return url
    ? <img className={styles.flag} src={url} alt={code} loading="lazy" />
    : <span className={styles.flagFallback}>{code?.slice(0, 3) ?? '?'}</span>
}

function QuickProb({ analysis }) {
  if (!analysis?.resultado) return null
  const best = analysis.resultado.reduce((m, r) => (r.cal ?? 0) > (m.cal ?? 0) ? r : m)
  const lvl = best.cal >= 0.65 ? styles.alta : best.cal >= 0.55 ? styles.media : styles.baja
  return (
    <div className={styles.probs}>
      {analysis.resultado.map((r, i) => (
        <div key={i} className={styles.probCol}>
          <span className={styles.probLab}>{r.label?.split(' ')[0]}</span>
          <span className={`${styles.probVal} ${r === best ? lvl : ''}`}>
            {Math.round((r.cal ?? r.prob) * 100)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export default function MatchCard({ card }) {
  const { selectMatch } = useSport()
  const picks = card.analysis?.picks ?? []
  const hasPicks = picks.length > 0

  return (
    <button className={styles.card} onClick={() => selectMatch(card)}>
      <div className={styles.header}>
        <span className={styles.time}>{card.time ?? '—'}</span>
        {hasPicks && <span className={styles.badge}>✓ Picks</span>}
        {card.edge?.rows?.some(r => r.tier === 'FUERTE') && (
          <span className={styles.edgeBadge}>⚡ Edge</span>
        )}
      </div>

      <div className={styles.matchup}>
        <div className={styles.teamBlock}>
          <Flag url={card.home_flag} code={card.home_code} />
          <span className={styles.teamName}>{card.home}</span>
        </div>
        <span className={styles.vs}>vs</span>
        <div className={styles.teamBlock}>
          <Flag url={card.away_flag} code={card.away_code} />
          <span className={styles.teamName}>{card.away}</span>
        </div>
      </div>

      <QuickProb analysis={card.analysis} />

      {hasPicks && (
        <div className={styles.pickPreview}>
          {picks.slice(0, 2).map((p, i) => (
            <span key={i} className={styles.pickChip}>{p.pick}</span>
          ))}
        </div>
      )}
    </button>
  )
}
