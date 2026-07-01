import { useSport } from '../../hooks/useSport'
import Pill from '../common/Pill'

const pct = (x) => Math.round((x ?? 0) * 100) + '%'

const TIER_CONFIG = {
  FUERTE:     { bg: 'rgba(251,113,133,0.12)', color: '#fb7185', border: 'rgba(251,113,133,0.2)', label: 'FUERTE' },
  MODERADO:   { bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.2)',  label: 'MOD' },
  BAJO:       { bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa', border: 'rgba(96,165,250,0.2)',  label: 'BAJO' },
  PASAR:      { bg: 'rgba(255,255,255,0.04)', color: '#4d5e73', border: 'rgba(255,255,255,0.08)', label: 'pass' },
  'NO-APTO':  { bg: 'rgba(255,255,255,0.04)', color: '#4d5e73', border: 'rgba(255,255,255,0.08)', label: '—' },
  SOSPECHOSO: { bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.2)',  label: 'SUSP' },
}

function ProbBar({ prob, cal }) {
  const val = cal ?? prob ?? 0
  const p = Math.round(val * 100)
  const colorCls = p >= 65
    ? 'from-[rgba(94,234,212,0.7)] to-[#5eead4]'
    : p >= 55
      ? 'from-[rgba(96,165,250,0.7)] to-[#60a5fa]'
      : 'from-[rgba(77,94,115,0.5)] to-[#4d5e73]'
  const textCls = p >= 65 ? 'text-accent' : p >= 55 ? 'text-body' : 'text-muted'
  return (
    <div className="flex items-center gap-2 flex-1">
      <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div
          className={`h-full rounded-full bg-gradient-to-r ${colorCls} transition-all duration-300`}
          style={{ width: p + '%' }}
        />
      </div>
      <span className={`text-sm font-bold tabular w-9 text-right ${textCls}`}>{p}%</span>
    </div>
  )
}

function EdgeRow({ r }) {
  const cfg = TIER_CONFIG[r.tier] ?? TIER_CONFIG.PASAR
  const hasEdge = r.tier !== 'PASAR' && r.tier !== 'NO-APTO'
  const eg = hasEdge
    ? (r.edge >= 0 ? '+' : '') + (Math.round(r.edge * 1000) / 10) + '%'
    : '—'
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-white/[0.04]">
      <span className="text-sm text-body flex-1 min-w-0 truncate">{r.label}</span>
      <span className="text-xs text-subtle tabular hidden sm:block shrink-0">
        m {pct(r.p_model)} · mkt {pct(r.p_market)}
      </span>
      <span className={`text-sm font-bold tabular w-14 text-right shrink-0 ${hasEdge ? 'text-accent' : 'text-subtle'}`}>
        {eg}
      </span>
      <span
        className="text-[11px] px-2 py-0.5 rounded-md font-semibold shrink-0"
        style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}
      >
        {cfg.label}
      </span>
    </div>
  )
}

function MktRow({ label, prob, cal, pickLevel }) {
  const isPick = Boolean(pickLevel)
  return (
    <div className={`flex items-center gap-3 py-2 rounded-lg px-2 -mx-2 transition-colors ${isPick ? 'bg-[rgba(94,234,212,0.04)]' : ''}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPick ? 'bg-accent' : 'bg-transparent'}`} />
      <span className={`text-sm flex-1 min-w-0 truncate ${isPick ? 'text-body font-medium' : 'text-muted'}`}>{label}</span>
      {cal != null && <span className="text-[10px] text-subtle shrink-0">cal</span>}
      <ProbBar prob={prob} cal={cal} />
    </div>
  )
}

function pickLevel(label, pickMap) {
  if (pickMap[label]) return pickMap[label]
  for (const [k, v] of Object.entries(pickMap)) {
    if (label.startsWith(k) || k.startsWith(label)) return v
  }
  return null
}

function SectionTitle({ children }) {
  return (
    <h4 className="text-[10px] text-subtle uppercase tracking-widest font-semibold mb-1 mt-6 first:mt-0">
      {children}
    </h4>
  )
}

function SoccerTeamContent({ match }) {
  const a = match.analysis
  const edge = match.edge
  if (!a) return <p className="text-sm text-muted py-4">Sin análisis disponible.</p>

  const pickMap = Object.fromEntries((a.picks ?? []).map(p => [p.pick, p.level]))

  return (
    <div>
      {edge?.rows?.length > 0 && (
        <section>
          <SectionTitle>Edge vs mercado · {edge.provider}</SectionTitle>
          {edge.rows.map((r, i) => <EdgeRow key={i} r={r} />)}
          <p className="text-[11px] text-subtle mt-2">SUSP = edge {'>'} 20%: probable error del modelo.</p>
        </section>
      )}

      <section>
        <SectionTitle>Resultado 1X2</SectionTitle>
        {a.resultado?.map((r, i) => (
          <MktRow key={i} label={r.label} prob={r.prob} cal={r.cal}
            pickLevel={pickLevel(r.label, pickMap)} />
        ))}
      </section>

      <section>
        <SectionTitle>Goles</SectionTitle>
        {[
          ['Over 1.5', a.goles?.over15],
          ['Over 2.5', a.goles?.over25],
          ['Over 3.5', a.goles?.over35],
          ['Ambos marcan (BTTS)', a.goles?.btts],
        ].filter(([, v]) => v != null).map(([lab, p]) => (
          <MktRow key={lab} label={lab} prob={p}
            pickLevel={pickLevel(lab, pickMap)} />
        ))}
      </section>

      {a.valla && (
        <section>
          <SectionTitle>Valla invicta</SectionTitle>
          <MktRow label={match.home} prob={a.valla.home} pickLevel={pickLevel(match.home, pickMap)} />
          <MktRow label={match.away} prob={a.valla.away} pickLevel={pickLevel(match.away, pickMap)} />
        </section>
      )}

      {a.corners && (
        <section>
          <SectionTitle>Corners · esp. {a.corners.exp}</SectionTitle>
          {[
            ['Over 8.5', a.corners.o85],
            ['Over 9.5', a.corners.o95],
            ['Over 10.5', a.corners.o105],
          ].map(([lab, p]) => (
            <MktRow key={lab} label={lab} prob={p} pickLevel={pickLevel(lab, pickMap)} />
          ))}
        </section>
      )}
    </div>
  )
}

function MLBTeamContent({ match }) {
  const raw = match._mlbRaw
  if (!raw) return <p className="text-sm text-muted py-4">Sin datos del equipo.</p>
  return (
    <div>
      <section>
        <SectionTitle>Análisis</SectionTitle>
        {(raw.logros ?? []).map((l, i) => (
          <MktRow key={i} label={`${l.market}: ${l.pick}`} prob={l.prob / 100} />
        ))}
      </section>
      {(raw.analisis ?? []).length > 0 && (
        <section>
          <SectionTitle>Contexto</SectionTitle>
          {raw.analisis.map((a, i) => (
            <p key={i} className="text-sm text-muted py-1 leading-relaxed">{a}</p>
          ))}
        </section>
      )}
    </div>
  )
}

export default function TeamTab({ match }) {
  const { activeSubTeam, setSubTeam } = useSport()
  const isSoccer = !match._mlbRaw

  return (
    <div>
      <div className="flex gap-1 mb-5 p-1 rounded-xl inline-flex" style={{ background: 'rgba(20,27,39,0.8)' }}>
        {['home', 'away'].map(side => {
          const label = side === 'home' ? match.home : match.away
          const flag  = side === 'home' ? match.home_flag : match.away_flag
          return (
            <button
              key={side}
              onClick={() => setSubTeam(side)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeSubTeam === side
                  ? 'text-body'
                  : 'text-muted hover:text-body'
              }`}
              style={activeSubTeam === side ? { background: 'rgba(255,255,255,0.07)' } : {}}
            >
              {flag && <img className="w-4 h-4 rounded-sm object-cover" src={flag} alt="" />}
              <span className="truncate max-w-[110px]">{label}</span>
            </button>
          )
        })}
      </div>

      {isSoccer
        ? <SoccerTeamContent match={match} />
        : <MLBTeamContent match={match} />
      }
    </div>
  )
}
