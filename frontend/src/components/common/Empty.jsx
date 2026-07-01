export default function Empty({ title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-10 h-10 rounded-full bg-surface-2 flex items-center justify-center mb-3">
        <span className="text-subtle text-lg leading-none">○</span>
      </div>
      <p className="text-sm font-medium text-muted mb-1">{title || 'Sin datos disponibles'}</p>
      {subtitle && <p className="text-xs text-subtle max-w-xs leading-relaxed">{subtitle}</p>}
    </div>
  )
}
