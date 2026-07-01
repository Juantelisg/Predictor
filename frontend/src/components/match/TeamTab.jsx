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

const pctColor = (p) => p >= 65 ? 'text-accent' : p >= 55 ? 'text-sky' : 'text-muted'

// ¿ese pick se habría cumplido en un partido cuyo (goles a favor, en contra) fue (gf, ga)?
// null = mercado sin histórico por partido (corners/tarjetas).
function hitOf(kind, line, gf, ga) {
  const total = gf + ga
  switch (kind) {
    case 'win':    return gf > ga
    case 'draw':   return gf === ga
    case '12':     return gf !== ga
    case 'dc':     return gf >= ga            // doble oportunidad = no perder
    case 'over':   return total > line
    case 'under':  return total < line
    case 'btts':   return gf > 0 && ga > 0
    case 'nobtts': return !(gf > 0 && ga > 0)
    case 'cs':     return ga === 0            // valla invicta
    default:       return null
  }
}

// Strip de ritmo del pick: un slot por partido (viejo -> reciente). ✓ verde si el pick
// se cumplió, ✗ rojo si no. games = [[gf, ga], ...] del equipo de referencia.
function HitStrip({ games, kind, line }) {
  if (kind == null || !games?.length) return <span className="text-xs text-subtle">—</span>
  return (
    <div className="flex gap-0.5 shrink-0">
      {games.map(([gf, ga], i) => {
        const hit = hitOf(kind, line, gf, ga)
        const s = hit
          ? { bg: 'rgba(94,234,212,0.15)', color: '#5eead4', ch: '✓' }
          : { bg: 'rgba(251,113,133,0.15)', color: '#fb7185', ch: '✗' }
        return (
          <span
            key={i}
            title={`${gf}-${ga}`}
            className="inline-flex items-center justify-center rounded-[3px] text-[9px] font-bold leading-none w-3.5 h-4"
            style={{ background: s.bg, color: s.color }}
          >
            {s.ch}
          </span>
        )
      })}
    </div>
  )
}

// Grupos de mercados según el modo (general | home | away). Cada fila lleva el mercado,
// el pick, la prob del modelo, y (kind, line, refSide) para computar el strip de ritmo.
// En modo equipo el ritmo es relativo a ese equipo; en general, los mercados de partido
// (goles/corners/tarjetas) usan al local como referencia.
function buildGroups(a, mode) {
  const res = a.resultado ?? []            // [home, draw, away]
  const isTeam = mode === 'home' || mode === 'away'
  const anchor = isTeam ? mode : 'home'
  const groups = []

  // 1X2
  const g1 = []
  if (mode === 'general') {
    if (res[0]) g1.push({ market: '1X2', pick: res[0].label, prob: res[0].cal ?? res[0].prob, kind: 'win', refSide: 'home' })
    if (res[1]) g1.push({ market: '1X2', pick: res[1].label, prob: res[1].cal ?? res[1].prob, kind: 'draw', refSide: 'home' })
    if (res[2]) g1.push({ market: '1X2', pick: res[2].label, prob: res[2].cal ?? res[2].prob, kind: 'win', refSide: 'away' })
  } else {
    const team = mode === 'home' ? a.home : a.away
    const r = mode === 'home' ? res[0] : res[2]
    if (r) g1.push({ market: 'Resultado', pick: r.label, prob: r.cal ?? r.prob, kind: 'win', refSide: mode })
    const dcKey = mode === 'home' ? '1X' : 'X2'
    if (a.doble?.[dcKey] != null) g1.push({ market: 'Doble oportunidad', pick: `${team} o empate`, prob: a.doble[dcKey], kind: 'dc', refSide: mode })
  }
  if (g1.length) groups.push({ title: '1X2', rows: g1 })

  // Goles
  const g = a.goles ?? {}
  const gg = []
  if (g.over15 != null) gg.push({ market: 'Goles', pick: 'Over 1.5', prob: g.over15, kind: 'over', line: 1.5, refSide: anchor })
  if (g.over25 != null) gg.push({ market: 'Goles', pick: 'Over 2.5', prob: g.over25, kind: 'over', line: 2.5, refSide: anchor })
  if (g.over35 != null) gg.push({ market: 'Goles', pick: 'Over 3.5', prob: g.over35, kind: 'over', line: 3.5, refSide: anchor })
  if (g.btts != null)   gg.push({ market: 'BTTS', pick: 'Ambos marcan', prob: g.btts, kind: 'btts', refSide: anchor })
  if (gg.length) groups.push({ title: 'Goles', rows: gg })

  // Valla invicta
  const vg = []
  if (mode === 'general') {
    if (a.valla?.home != null) vg.push({ market: 'Valla invicta', pick: `${a.home} sin recibir gol`, prob: a.valla.home, kind: 'cs', refSide: 'home' })
    if (a.valla?.away != null) vg.push({ market: 'Valla invicta', pick: `${a.away} sin recibir gol`, prob: a.valla.away, kind: 'cs', refSide: 'away' })
  } else {
    const team = mode === 'home' ? a.home : a.away
    const v = mode === 'home' ? a.valla?.home : a.valla?.away
    if (v != null) vg.push({ market: 'Valla invicta', pick: `${team} sin recibir gol`, prob: v, kind: 'cs', refSide: mode })
  }
  if (vg.length) groups.push({ title: 'Valla invicta', rows: vg })

  // Corners (sin histórico por partido -> strip '—')
  if (a.corners) {
    const cc = []
    ;[['Over 8.5', a.corners.o85], ['Over 9.5', a.corners.o95], ['Over 10.5', a.corners.o105]]
      .forEach(([pick, v]) => { if (v != null) cc.push({ market: 'Corners', pick, prob: v, kind: null, refSide: anchor }) })
    if (cc.length) groups.push({ title: `Corners · esp. ${a.corners.exp}`, rows: cc })
  }

  // Tarjetas (sin histórico por partido -> strip '—')
  if (a.cards) {
    const kk = []
    ;[['Over 2.5', a.cards.o25], ['Over 3.5', a.cards.o35], ['Over 4.5', a.cards.o45]]
      .forEach(([pick, v]) => { if (v != null) kk.push({ market: 'Tarjetas', pick, prob: v, kind: null, refSide: anchor }) })
    if (kk.length) groups.push({ title: `Tarjetas · esp. ${a.cards.exp}`, rows: kk })
  }

  return groups
}

// Deriva kind/line/subject de un pick confiable para poder mostrarle su strip de ritmo.
function pickInfo(p, a) {
  const t = p.pick, m = p.market
  if (m === 'Resultado') return { kind: 'win', subject: t === a.resultado?.[2]?.label ? 'away' : 'home' }
  if (m.startsWith('Doble')) {
    if (t.includes('Sin empate')) return { kind: '12', subject: 'match' }
    return { kind: 'dc', subject: t.startsWith(a.away) ? 'away' : 'home' }
  }
  if (m === 'Goles') { const mm = t.match(/([\d.]+)/); return { kind: t.startsWith('Over') ? 'over' : 'under', line: mm ? parseFloat(mm[1]) : null, subject: 'match' } }
  if (m === 'BTTS') return { kind: t.startsWith('Ambos') ? 'btts' : 'nobtts', subject: 'match' }
  return { kind: null, subject: 'match' }
}
const resolveRef = (subject, mode) => subject === 'match' ? (mode === 'general' ? 'home' : mode) : subject

function GroupedTable({ groups, lastGames, pickMap }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <div className="min-w-[520px] px-1">
        <div className="flex items-center gap-3 pb-2 border-b border-white/[0.06]">
          <span className="text-[10px] text-subtle uppercase tracking-wider flex-1">Mercado</span>
          <span className="text-[10px] text-subtle uppercase tracking-wider w-24 text-right">Prob. modelo</span>
          <span className="text-[10px] text-subtle uppercase tracking-wider w-20 text-center">Últ. 5</span>
          <span className="text-[10px] text-subtle uppercase tracking-wider w-40 text-center">Últ. 10</span>
        </div>
        {groups.map((grp, gi) => (
          <div key={gi}>
            <div className="text-[10px] text-accent/80 uppercase tracking-widest font-semibold pt-4 pb-1">{grp.title}</div>
            {grp.rows.map((r, i) => {
              const p = Math.round((r.prob ?? 0) * 100)
              const isPick = pickMap && Boolean(pickLevel(r.pick, pickMap))
              const games = lastGames?.[r.refSide] ?? []
              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 py-2 border-b border-white/[0.04] ${isPick ? 'bg-[rgba(94,234,212,0.04)]' : ''}`}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPick ? 'bg-accent' : 'bg-transparent'}`} />
                    <span className={`text-sm truncate ${isPick ? 'text-body font-medium' : 'text-body'}`}>{r.pick}</span>
                  </div>
                  <span className={`text-sm font-bold tabular w-24 text-right ${pctColor(p)}`}>{p}%</span>
                  <div className="w-20 flex justify-center"><HitStrip games={games.slice(-5)} kind={r.kind} line={r.line} /></div>
                  <div className="w-40 flex justify-center"><HitStrip games={games.slice(-10)} kind={r.kind} line={r.line} /></div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function SoccerTeamContent({ match, mode }) {
  const a = match.analysis
  const edge = match.edge
  if (!a) return <p className="text-sm text-muted py-4">Sin análisis disponible.</p>

  const pickMap = Object.fromEntries((a.picks ?? []).map(p => [p.pick, p.level]))
  const lastGames = a.last_games ?? {}

  const pickRows = (a.picks ?? []).map(p => {
    const info = pickInfo(p, a)
    return { market: p.market, pick: p.pick, prob: p.prob, kind: info.kind, line: info.line,
             subject: info.subject, refSide: resolveRef(info.subject, mode) }
  })
  const shownPicks = mode === 'general'
    ? pickRows
    : pickRows.filter(r => r.subject === 'match' || r.subject === mode)

  const groups = []
  if (shownPicks.length) groups.push({ title: 'Picks confiables', rows: shownPicks })
  buildGroups(a, mode).forEach(gr => groups.push(gr))

  return (
    <div>
      {edge?.rows?.length > 0 && (
        <section>
          <SectionTitle>Edge vs mercado · {edge.provider}</SectionTitle>
          {edge.rows.map((r, i) => <EdgeRow key={i} r={r} />)}
          <p className="text-[11px] text-subtle mt-2">SUSP = edge {'>'} 20%: probable error del modelo.</p>
        </section>
      )}

      <section className="mt-6">
        <GroupedTable groups={groups} lastGames={lastGames} pickMap={pickMap} />
        <p className="text-[11px] text-subtle mt-3 leading-relaxed">
          <span className="text-body">Prob. modelo</span> = probabilidad estimada por el modelo (no es el histórico).{' '}
          <span className="text-accent font-semibold">✓</span>/<span className="text-hot font-semibold">✗</span> Últ. 5 / 10 = si ese pick se
          habría cumplido en cada uno de los últimos partidos del equipo (viejo → reciente).
          {mode === 'general' && ' En General, los mercados de partido usan al local como referencia.'}{' '}
          Corners/tarjetas: sin histórico por partido (—).
        </p>
      </section>
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

  const opts = [
    { key: 'general', label: 'General' },
    { key: 'home', label: match.home, flag: match.home_flag },
    { key: 'away', label: match.away, flag: match.away_flag },
  ]

  return (
    <div>
      <div className="flex gap-1 mb-5 p-1 rounded-xl inline-flex" style={{ background: 'rgba(20,27,39,0.8)' }}>
        {opts.map(o => (
          <button
            key={o.key}
            onClick={() => setSubTeam(o.key)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeSubTeam === o.key ? 'text-body' : 'text-muted hover:text-body'
            }`}
            style={activeSubTeam === o.key ? { background: 'rgba(255,255,255,0.07)' } : {}}
          >
            {o.flag && <img className="w-4 h-4 rounded-sm object-cover" src={o.flag} alt="" />}
            <span className="truncate max-w-[110px]">{o.label}</span>
          </button>
        ))}
      </div>

      {isSoccer
        ? <SoccerTeamContent match={match} mode={activeSubTeam} />
        : <MLBTeamContent match={match} />
      }
    </div>
  )
}
