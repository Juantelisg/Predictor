export default function Skeleton({ rows = 4 }) {
  return (
    <div className="flex flex-col gap-3 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl bg-surface-2 overflow-hidden relative"
          style={{ height: 72, opacity: Math.max(0.3, 1 - i * 0.18) }}
        >
          <div
            className="absolute inset-0 animate-shimmer"
            style={{
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent)',
              backgroundSize: '600px 100%',
            }}
          />
        </div>
      ))}
    </div>
  )
}
