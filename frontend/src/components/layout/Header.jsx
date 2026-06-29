import { useQuery } from '@tanstack/react-query'
import { getBudget } from '../../api/ticket'
import { useSport } from '../../hooks/useSport'
import { useDate } from '../../hooks/useDate'
import styles from './Header.module.css'

const SPORTS = [
  { id: 'soccer', label: '⚽ Soccer' },
  { id: 'mlb',    label: '⚾ MLB' },
  { id: 'nfl',    label: '🏈 NFL' },
  { id: 'nba',    label: '🏀 NBA' },
]

export default function Header() {
  const { sport, setSport } = useSport()
  const date = useDate()
  const { data: budget } = useQuery({
    queryKey: ['budget'],
    queryFn: getBudget,
    staleTime: 60_000,
  })

  return (
    <header className={styles.header}>
      <div className={styles.bar}>
        <div className={styles.brand}>
          <span className={styles.dot} />
          <span>predictor</span>
          <span className={styles.brandSub}>/ análisis</span>
        </div>
        <div className={styles.spacer} />
        <span className={styles.chip}>{date}</span>
        {budget && (
          <span className={styles.chip}>
            API <strong>{budget.remaining}/{budget.limit}</strong>
          </span>
        )}
      </div>
      <nav className={styles.nav}>
        {SPORTS.map(s => (
          <button
            key={s.id}
            className={`${styles.tab} ${sport === s.id ? styles.active : ''}`}
            onClick={() => setSport(s.id)}
          >
            {s.label}
          </button>
        ))}
      </nav>
    </header>
  )
}
