import styles from './Pill.module.css'

const VARIANTS = { alta: 'alta', media: 'media', baja: 'baja', pass: 'pass', strong: 'alta', moderate: 'media' }

export default function Pill({ label, variant }) {
  const v = VARIANTS[variant?.toLowerCase()] || 'pass'
  return <span className={`${styles.pill} ${styles[v]}`}>{label}</span>
}
