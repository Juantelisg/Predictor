import styles from './Empty.module.css'

export default function Empty({ title, subtitle }) {
  return (
    <div className={styles.wrap}>
      <p className={styles.title}>{title || 'Sin datos disponibles'}</p>
      {subtitle && <p className={styles.sub}>{subtitle}</p>}
    </div>
  )
}
