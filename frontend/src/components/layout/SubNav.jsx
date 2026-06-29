import { useSport } from '../../hooks/useSport'
import styles from './SubNav.module.css'

const SUBTABS = [
  { id: 'today',  label: 'Hoy' },
  { id: 'edge',   label: 'Edge' },
  { id: 'record', label: 'Track Record' },
]

export default function SubNav() {
  const { subtab, setSubtab } = useSport()

  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>
        {SUBTABS.map(s => (
          <button
            key={s.id}
            className={`${styles.btn} ${subtab === s.id ? styles.active : ''}`}
            onClick={() => setSubtab(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}
