import styles from './OffSeason.module.css'

const SEASON_DATES = {
  nfl: { start: 'Septiembre 2026', event: 'Temporada regular NFL 2026-27' },
  nba: { start: 'Octubre 2026',    event: 'Temporada regular NBA 2026-27' },
}

export default function OffSeason({ sport }) {
  const meta = SEASON_DATES[sport] ?? { start: 'Próximamente', event: `Temporada ${sport.toUpperCase()}` }

  return (
    <div className={styles.wrap}>
      <div className={styles.icon}>{sport === 'nfl' ? '🏈' : '🏀'}</div>
      <h3 className={styles.title}>{meta.event}</h3>
      <p className={styles.sub}>Temporada off. Volvemos en <strong>{meta.start}</strong>.</p>
      <p className={styles.note}>
        El modelo estará listo cuando empiece la temporada. Las predicciones, edge y
        track record van a aparecer acá automáticamente.
      </p>
    </div>
  )
}
