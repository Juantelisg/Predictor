import styles from './Skeleton.module.css'

export default function Skeleton({ rows = 4 }) {
  return (
    <div className={styles.list}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={styles.skel} />
      ))}
    </div>
  )
}
