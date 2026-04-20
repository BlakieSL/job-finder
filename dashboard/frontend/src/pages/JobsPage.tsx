import { useEffect, useState, useRef } from "react"
import { JobDetail } from "./JobDetail"

// ── types ─────────────────────────────────────────────────────────────────────
type Job = {
  id: string; source: string; position: string; company: string
  seniority: string; salary: string; fit_score: number | null
  status: string; expires_at: string; posted_at: string | null; url: string
}
type Stats = Record<string, number>
type JobRef = { id: string; source: string } | null
type SortOpt = "fit_score" | "company" | "expires_at" | "posted_at" | "position"

// ── helpers ───────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, { dot: string; bg: string; text: string }> = {
  new:       { dot: "bg-gray-400",   bg: "bg-gray-100",   text: "text-gray-600" },
  scored:    { dot: "bg-blue-500",   bg: "bg-blue-50",    text: "text-blue-700" },
  tailored:  { dot: "bg-purple-500", bg: "bg-purple-50",  text: "text-purple-700" },
  pdf_ready: { dot: "bg-amber-500",  bg: "bg-amber-50",   text: "text-amber-700" },
  applied:   { dot: "bg-green-500",  bg: "bg-green-50",   text: "text-green-700" },
  expired:   { dot: "bg-red-400",    bg: "bg-red-50",     text: "text-red-600" },
  inactive:  { dot: "bg-red-300",    bg: "bg-red-50",     text: "text-red-500" },
}
const STATUSES = ["new", "scored", "tailored", "pdf_ready", "applied", "expired", "inactive"]
const SENIORITIES = ["Junior", "Mid", "Senior", "Trainee", "Lead", "Manager"]
const SOURCES = ["justjoinit", "nofluffjobs"]
const POSTED_FILTERS: { key: string; label: string; days: number }[] = [
  { key: "",   label: "Any time",     days: 0 },
  { key: "0.5", label: "Last 12 hours", days: 0.5 },
  { key: "1",  label: "Last 24 hours", days: 1 },
  { key: "3",  label: "Last 3 days",   days: 3 },
  { key: "7",  label: "Last week",     days: 7 },
]

function statusStyle(s: string) {
  return STATUS_COLORS[s] ?? { dot: "bg-gray-400", bg: "bg-gray-100", text: "text-gray-600" }
}
function statusLabel(s: string) {
  if (s === "pdf_ready") return "PDF ready"
  return s.charAt(0).toUpperCase() + s.slice(1)
}
function scoreColor(score: number | null) {
  if (score == null) return "text-gray-400"
  if (score >= 80) return "text-emerald-600"
  if (score >= 60) return "text-amber-600"
  return "text-red-500"
}
function companyInitials(name: string) {
  return name.split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase() ?? "").join("")
}
const AVATAR_COLORS = [
  "bg-violet-500","bg-blue-500","bg-cyan-500","bg-teal-500",
  "bg-emerald-500","bg-rose-500","bg-orange-500","bg-pink-500",
]
function avatarColor(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

// ── Console ───────────────────────────────────────────────────────────────────
function Console({ log, running, onClear, onStop }: {
  log: string; running: boolean; onClear: () => void; onStop: () => void
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const logRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  if (!log) return null

  return (
    <div className={`flex flex-col bg-gray-950 rounded-lg overflow-hidden border border-gray-800
      ${fullscreen ? "fixed inset-4 z-50 rounded-xl shadow-2xl" : ""}`}>
      <div className="flex items-center px-3 py-1.5 bg-gray-900 border-b border-gray-800">
        <span className="text-xs font-mono flex-1">
          {running
            ? <span className="text-green-400 animate-pulse">● Running…</span>
            : <span className="text-gray-500">● Output</span>}
        </span>
        {running && (
          <button onClick={onStop}
            className="text-red-400 hover:text-red-300 text-xs px-2 py-0.5 rounded border border-red-700 hover:border-red-500 transition-colors font-medium">
            Stop
          </button>
        )}
        <button onClick={() => setFullscreen(f => !f)}
          className="ml-2 text-gray-400 hover:text-gray-200 text-xs px-2 py-0.5 rounded border border-gray-700 hover:border-gray-500 transition-colors">
          {fullscreen ? "Exit fullscreen" : "Fullscreen"}
        </button>
        <button onClick={onClear}
          className="ml-2 text-gray-400 hover:text-red-400 text-xs px-2 py-0.5 rounded border border-gray-700 hover:border-red-700 transition-colors">
          Clear
        </button>
      </div>
      <pre ref={logRef}
        className="overflow-auto text-xs font-mono text-green-400 p-3 leading-relaxed whitespace-pre-wrap"
        style={fullscreen ? { flex: 1 } : { height: 160 }}>
        {log}
      </pre>
    </div>
  )
}

// ── Action popover ───────────────────────────────────────────────────────────
const POSTED_OPTIONS: { label: string; hours: string }[] = [
  { label: "All time",     hours: "" },
  { label: "Last 12 hours", hours: "12" },
  { label: "Last 24 hours", hours: "24" },
  { label: "Last 3 days",   hours: "72" },
  { label: "Last week",     hours: "168" },
]

function ActionPopover({ label, color, dot, showMinScore, onRun, onClose }: {
  label: string; color: string; dot: string
  showMinScore: boolean; onRun: (minScore: number, postedHours: string) => void; onClose: () => void
}) {
  const [minScore, setMinScore] = useState(59)
  const [postedHours, setPostedHours] = useState("")
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [onClose])

  return (
    <div ref={ref} className="absolute top-full left-0 mt-1 z-20 bg-white rounded-lg border border-gray-200 shadow-lg p-3 min-w-[200px]">
      <p className="text-xs font-semibold text-gray-700 mb-2">{label}</p>

      {showMinScore && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-gray-500">Min score</span>
          <input type="number" min={0} max={100} value={minScore}
            onChange={e => setMinScore(Math.max(0, Math.min(100, Number(e.target.value))))}
            className="w-14 h-6 text-xs text-center rounded border border-gray-200 bg-white focus:outline-none focus:ring-1 focus:ring-violet-400" />
        </div>
      )}

      <div className="flex flex-col gap-0.5 mb-3">
        <span className="text-xs text-gray-500 mb-0.5">Posted within</span>
        {POSTED_OPTIONS.map(o => (
          <button key={o.hours || "all"} onClick={() => setPostedHours(o.hours)}
            className={`text-xs px-2 py-1 rounded text-left transition-colors
              ${postedHours === o.hours ? "bg-violet-50 text-violet-700 font-medium" : "text-gray-600 hover:bg-gray-50"}`}>
            {o.label}
          </button>
        ))}
      </div>

      <button onClick={() => { onRun(minScore, postedHours); onClose() }}
        className={`w-full h-7 text-xs rounded-lg border font-medium flex items-center justify-center gap-1.5 transition-colors ${color}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        Run {label}
      </button>
    </div>
  )
}

// ── Global action bar ─────────────────────────────────────────────────────────
function GlobalActions({ onDone }: { onDone: () => void }) {
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState("")
  const [openPopover, setOpenPopover] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  function runAction(endpoint: string) {
    setLog("")
    setRunning(true)
    setOpenPopover(null)
    const controller = new AbortController()
    abortRef.current = controller
    fetch(endpoint, { method: "POST", signal: controller.signal }).then(async res => {
      const contentType = res.headers.get("content-type") ?? ""
      if (contentType.includes("application/json")) {
        const data = await res.json()
        setLog(JSON.stringify(data, null, 2) + "\n")
        setRunning(false)
        onDone()
        return
      }
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const text = decoder.decode(value)
          for (const line of text.split("\n").filter(l => l.startsWith("data: "))) {
            const data = line.slice(6)
            if (data === "[DONE]") { setRunning(false); onDone(); return }
            setLog(prev => prev + data + "\n")
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") throw e
      }
      setRunning(false)
    }).catch(e => {
      if ((e as Error).name === "AbortError") {
        setLog(prev => prev + "\n⛔ Stopped.\n")
        setRunning(false)
        onDone()
      } else {
        setLog(prev => prev + `\nError: ${e}\n`)
        setRunning(false)
      }
    })
  }

  function stopAction() {
    abortRef.current?.abort()
  }

  function buildUrl(base: string, minScore?: number, postedHours?: string) {
    const p = new URLSearchParams()
    if (minScore !== undefined) p.set("min_score", String(minScore))
    if (postedHours) p.set("posted_within", postedHours)
    const qs = p.toString()
    return qs ? `${base}?${qs}` : base
  }

  const btnBase = "h-7 px-3 text-xs rounded-lg border font-medium flex items-center gap-1.5 disabled:opacity-40 transition-colors"

  return (
    <div className="mb-4 rounded-xl border border-gray-200 bg-white">
      <div className="flex flex-wrap gap-x-3 gap-y-2 items-center px-4 py-3 border-b border-gray-100 overflow-visible relative">

        <button disabled={running} onClick={() => runAction("/api/actions/scrape")}
          className={`${btnBase} border-gray-200 text-gray-700 hover:bg-gray-50`}>
          <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
          Scrape
        </button>

        <div className="relative">
          <button disabled={running} onClick={() => setOpenPopover(openPopover === "score" ? null : "score")}
            className={`${btnBase} border-blue-200 text-blue-700 hover:bg-blue-50`}>
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            Score
          </button>
          {openPopover === "score" && (
            <ActionPopover label="Score" color="border-blue-200 text-blue-700 hover:bg-blue-50" dot="bg-blue-500"
              showMinScore={false}
              onRun={(_ms, ph) => runAction(buildUrl("/api/actions/score", undefined, ph))}
              onClose={() => setOpenPopover(null)} />
          )}
        </div>

        <div className="relative">
          <button disabled={running} onClick={() => setOpenPopover(openPopover === "tailor" ? null : "tailor")}
            className={`${btnBase} border-violet-200 text-violet-700 hover:bg-violet-50`}>
            <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
            Tailor
          </button>
          {openPopover === "tailor" && (
            <ActionPopover label="Tailor" color="border-violet-200 text-violet-700 hover:bg-violet-50" dot="bg-violet-500"
              showMinScore={true}
              onRun={(ms, ph) => runAction(buildUrl("/api/actions/tailor", ms, ph))}
              onClose={() => setOpenPopover(null)} />
          )}
        </div>

        <div className="relative">
          <button disabled={running} onClick={() => setOpenPopover(openPopover === "pdf" ? null : "pdf")}
            className={`${btnBase} border-amber-200 text-amber-700 hover:bg-amber-50`}>
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            Generate PDFs
          </button>
          {openPopover === "pdf" && (
            <ActionPopover label="Generate PDFs" color="border-amber-200 text-amber-700 hover:bg-amber-50" dot="bg-amber-500"
              showMinScore={true}
              onRun={(ms, ph) => runAction(buildUrl("/api/actions/generate-pdf-batch", ms, ph))}
              onClose={() => setOpenPopover(null)} />
          )}
        </div>

        <button disabled={running} onClick={() => runAction("/api/actions/drop-expired")}
          className={`${btnBase} border-red-200 text-red-700 hover:bg-red-50`}>
          <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
          Drop expired
        </button>

        {running && (
          <span className="text-xs text-gray-400 animate-pulse ml-auto">Running…</span>
        )}
      </div>

      <Console log={log} running={running} onClear={() => setLog("")} onStop={stopAction} />
    </div>
  )
}

// ── Navbar ────────────────────────────────────────────────────────────────────
function Navbar({ search, onSearch, sidebarOpen, onToggleSidebar }: {
  search: string; onSearch: (v: string) => void
  sidebarOpen: boolean; onToggleSidebar: () => void
}) {
  return (
    <header className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
      <div className="flex items-center gap-3 px-4 h-14">
        <button onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16"/>
          </svg>
        </button>
        <span className="font-bold text-gray-900 text-base whitespace-nowrap">Job Tracker</span>
        <div className="flex-1 max-w-xl relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
          </svg>
          <input type="text" placeholder="Search job title, company..."
            value={search} onChange={e => onSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-full bg-gray-50 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent transition"
          />
        </div>
      </div>
    </header>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({
  stats, status, seniority, source, minScore, postedWithin,
  onStatus, onSeniority, onSource, onMinScore, onPostedWithin, onReset,
}: {
  stats: Stats
  status: string; seniority: string; source: string; minScore: number; postedWithin: string
  onStatus: (v: string) => void; onSeniority: (v: string) => void
  onSource: (v: string) => void; onMinScore: (v: number) => void; onPostedWithin: (v: string) => void
  onReset: () => void
}) {
  const hasFilters = status || seniority || source || minScore > 0 || postedWithin

  return (
    <aside className="w-52 shrink-0 flex flex-col gap-4 pt-5 pb-8">

      {/* Reset */}
      {hasFilters && (
        <button onClick={onReset}
          className="text-xs text-violet-600 hover:text-violet-800 font-medium px-2 -mb-2 text-left">
          ✕ Clear all filters
        </button>
      )}

      {/* Pipeline */}
      <section>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-1.5">Pipeline</h3>
        <div className="flex flex-col gap-0.5">
          {[["", "All"], ...STATUSES.map(s => [s, s])].map(([val]) => {
            const sc = statusStyle(val)
            const count = val === "" ? Object.values(stats).reduce((a, b) => a + b, 0) : (stats[val] ?? 0)
            const active = status === val
            return (
              <button key={val || "all"} onClick={() => onStatus(val)}
                className={`flex items-center justify-between px-2 py-1.5 rounded-lg text-sm transition-colors
                  ${active ? "bg-violet-50 text-violet-700 font-medium" : "text-gray-600 hover:bg-gray-100"}`}>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${val === "" ? "bg-gray-300" : sc.dot}`} />
                  <span>{val === "" ? "All" : statusLabel(val)}</span>
                </div>
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium
                  ${active ? "bg-violet-100 text-violet-600" : "bg-gray-100 text-gray-500"}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Source */}
      <section>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-1.5">Source</h3>
        <div className="flex flex-col gap-0.5">
          {[["", "All sources"], ...SOURCES.map(s => [s, s])].map(([val, label]) => (
            <button key={val || "all"} onClick={() => onSource(val)}
              className={`flex items-center px-2 py-1.5 rounded-lg text-sm transition-colors
                ${source === val ? "bg-violet-50 text-violet-700 font-medium" : "text-gray-600 hover:bg-gray-100"}`}>
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* Posted within */}
      <section>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-1.5">Posted</h3>
        <div className="flex flex-col gap-0.5">
          {POSTED_FILTERS.map(f => (
            <button key={f.key || "any"} onClick={() => onPostedWithin(f.key)}
              className={`flex items-center px-2 py-1.5 rounded-lg text-sm transition-colors
                ${postedWithin === f.key ? "bg-violet-50 text-violet-700 font-medium" : "text-gray-600 hover:bg-gray-100"}`}>
              {f.label}
            </button>
          ))}
        </div>
      </section>

      {/* Seniority */}
      <section>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-1.5">Experience</h3>
        <div className="flex flex-col gap-0.5">
          {["", ...SENIORITIES].map(val => (
            <button key={val || "all"} onClick={() => onSeniority(val)}
              className={`flex items-center px-2 py-1.5 rounded-lg text-sm transition-colors
                ${seniority === val ? "bg-violet-50 text-violet-700 font-medium" : "text-gray-600 hover:bg-gray-100"}`}>
              {val || "All levels"}
            </button>
          ))}
        </div>
      </section>

      {/* Min score */}
      <section>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-2 mb-1.5">Min fit score</h3>
        <div className="px-2 flex flex-col gap-1.5">
          <div className="flex justify-between text-xs text-gray-500">
            <span>0</span>
            <span className="font-semibold text-violet-600">{minScore > 0 ? `${minScore}+` : "any"}</span>
            <span>100</span>
          </div>
          <input type="range" min={0} max={100} value={minScore}
            onChange={e => onMinScore(Number(e.target.value))}
            className="w-full accent-violet-500" />
          <div className="flex gap-1.5 flex-wrap">
            {[0, 60, 70, 80].map(v => (
              <button key={v} onClick={() => onMinScore(v)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors
                  ${minScore === v ? "bg-violet-100 border-violet-300 text-violet-700 font-medium" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}>
                {v === 0 ? "Any" : `${v}+`}
              </button>
            ))}
          </div>
        </div>
      </section>
    </aside>
  )
}

// ── Job card ──────────────────────────────────────────────────────────────────
function JobCard({ job, selected, onClick }: { job: Job; selected: boolean; onClick: () => void }) {
  const sc = statusStyle(job.status)
  return (
    <div onClick={onClick}
      className={`rounded-xl border cursor-pointer transition-all duration-150 p-4 flex gap-3
        ${job.status === "inactive" ? "bg-red-50/60" : "bg-white"}
        ${selected ? "border-violet-400 shadow-md ring-1 ring-violet-300" : "border-gray-200 hover:border-gray-300 hover:shadow-sm"}`}>
      <div className={`w-10 h-10 rounded-lg ${avatarColor(job.company)} flex items-center justify-center shrink-0 text-white text-sm font-bold`}>
        {companyInitials(job.company)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 text-sm leading-snug truncate">{job.position}</p>
            <p className="text-xs text-gray-500 mt-0.5">{job.company}
              <span className="text-gray-300 mx-1">·</span>
              <span className="text-gray-400">{job.source === "justjoinit" ? "JJI" : "NF"}</span>
            </p>
          </div>
          {job.fit_score != null && (
            <span className={`text-sm font-bold shrink-0 ${scoreColor(job.fit_score)}`}>{job.fit_score}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          {job.seniority && (
            <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{job.seniority}</span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1 ${sc.bg} ${sc.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
            {statusLabel(job.status)}
          </span>
          {job.salary && job.salary !== "Not disclosed" && (
            <span className="text-xs text-emerald-600 font-medium truncate max-w-[140px]">{job.salary}</span>
          )}
          {job.expires_at && (
            <span className="text-xs text-gray-300 ml-auto">{job.expires_at.slice(0, 10)}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sort bar ──────────────────────────────────────────────────────────────────
function SortBar({ total, sort, dir, onSort }: {
  total: number; sort: SortOpt; dir: "asc" | "desc"; onSort: (k: SortOpt) => void
}) {
  const opts: { key: SortOpt; label: string }[] = [
    { key: "fit_score", label: "Score" },
    { key: "posted_at", label: "Posted" },
    { key: "position",  label: "Title" },
    { key: "company",   label: "Company" },
    { key: "expires_at",label: "Expires" },
  ]
  return (
    <div className="flex items-center justify-between mb-3">
      <span className="text-sm text-gray-500">{total} offers</span>
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-400 mr-1">Sort:</span>
        {opts.map(o => (
          <button key={o.key} onClick={() => onSort(o.key)}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors
              ${sort === o.key ? "bg-violet-100 text-violet-700 font-semibold" : "text-gray-500 hover:bg-gray-100"}`}>
            {o.label}{sort === o.key ? (dir === "desc" ? " ↓" : " ↑") : ""}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [stats, setStats] = useState<Stats>({})
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [seniority, setSeniority] = useState("")
  const [source, setSource] = useState("")
  const [minScore, setMinScore] = useState(0)
  const [postedWithin, setPostedWithin] = useState("")
  const [sort, setSort] = useState<SortOpt>("fit_score")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [selected, setSelected] = useState<JobRef>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [detailWide, setDetailWide] = useState(false)

  useEffect(() => {
    fetch("/api/stats").then(r => r.json()).then(setStats)
  }, [refreshKey])

  useEffect(() => {
    const p = new URLSearchParams()
    if (status) p.set("status", status)
    if (search) p.set("search", search)
    if (source) p.set("source", source)
    p.set("min_score", String(minScore))
    fetch(`/api/jobs?${p}`).then(r => r.json()).then(setJobs)
  }, [status, search, source, minScore, refreshKey])

  function handleSort(key: SortOpt) {
    if (sort === key) setSortDir(d => d === "asc" ? "desc" : "asc")
    else { setSort(key); setSortDir(key === "fit_score" || key === "posted_at" ? "desc" : "asc") }
  }

  const postedCutoff = postedWithin
    ? new Date(Date.now() - parseFloat(postedWithin) * 86400000).toISOString().slice(0, 10)
    : ""

  const displayed = [...jobs]
    .filter(j => !seniority || j.seniority === seniority)
    .filter(j => !postedCutoff || (j.posted_at != null && j.posted_at >= postedCutoff))
    .sort((a, b) => {
      let cmp = sort === "fit_score"
        ? ((a.fit_score ?? -1) - (b.fit_score ?? -1))
        : String(a[sort] ?? "").localeCompare(String(b[sort] ?? ""))
      return sortDir === "asc" ? cmp : -cmp
    })

  function refresh() { setRefreshKey(k => k + 1) }

  function resetFilters() {
    setStatus(""); setSeniority(""); setSource(""); setMinScore(0); setPostedWithin("")
  }

  return (
    <>
      <Navbar search={search} onSearch={setSearch}
        sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen(o => !o)} />

      <div className="flex max-w-[1600px] mx-auto px-4 gap-6">
        {sidebarOpen && (
          <Sidebar
            stats={stats} status={status} seniority={seniority} source={source} minScore={minScore} postedWithin={postedWithin}
            onStatus={setStatus} onSeniority={setSeniority} onSource={setSource}
            onMinScore={setMinScore} onPostedWithin={setPostedWithin} onReset={resetFilters}
          />
        )}

        <main className="flex-1 min-w-0 py-5">
          <GlobalActions onDone={refresh} />
          <SortBar total={displayed.length} sort={sort} dir={sortDir} onSort={handleSort} />
          <div className="flex flex-col gap-2">
            {displayed.map(job => (
              <JobCard
                key={`${job.id}-${job.source}`} job={job}
                selected={selected?.id === job.id && selected?.source === job.source}
                onClick={() => setSelected(sel => {
                  const next = sel?.id === job.id && sel?.source === job.source ? null : { id: job.id, source: job.source }
                  if (!next) setDetailWide(false)
                  return next
                })}
              />
            ))}
            {displayed.length === 0 && (
              <div className="text-center py-20 text-gray-400 text-sm">No jobs match your filters</div>
            )}
          </div>
        </main>

        {selected && (
          <div className={`shrink-0 py-5 transition-all duration-200 ${detailWide ? "w-[55vw] min-w-[700px] max-w-[1000px]" : "w-[400px]"}`}>
            <div className="sticky top-20">
              <JobDetail
                jobRef={selected}
                onClose={() => { setSelected(null); setDetailWide(false) }}
                onUpdated={refresh}
                onJobLoaded={(hasValidCv) => setDetailWide(hasValidCv)}
              />
            </div>
          </div>
        )}
      </div>
    </>
  )
}
