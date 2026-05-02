import { useEffect, useState, useRef } from "react"
import { JobDetail } from "./JobDetail"

type Job = {
  id: string; source: string; position: string; company: string
  seniority: string; salary: string; fit_score: number | null
  status: string; expires_at: string; posted_at: string | null; url: string
  language: string; city: string | null
}
type Stats = Record<string, number>
type JobRef = { id: string; source: string } | null
type SortOpt = "fit_score" | "company" | "expires_at" | "posted_at" | "position" | "city"

const STATUS_DOT: Record<string, string> = {
  new: "bg-gray-400", scored: "bg-blue-500", tailored: "bg-purple-500",
  pdf_ready: "bg-amber-500", applied: "bg-green-500", expired: "bg-red-400", inactive: "bg-red-300",
}
const STATUS_ROW: Record<string, string> = {
  applied: "bg-green-50/40", expired: "bg-red-50/30", inactive: "bg-red-50/20",
}
const STATUSES = ["new", "scored", "tailored", "pdf_ready", "applied", "expired", "inactive"]
const SENIORITIES = ["Junior", "Mid", "Senior", "Trainee", "Lead", "Manager"]
const SOURCES = ["justjoinit", "nofluffjobs", "pracuj"]
const POSTED_FILTERS = [
  { key: "", label: "Any" }, { key: "0.5", label: "12h" }, { key: "1", label: "24h" },
  { key: "3", label: "3d" }, { key: "7", label: "1w" },
]

function statusLabel(s: string) { return s === "pdf_ready" ? "PDF" : s.charAt(0).toUpperCase() + s.slice(1) }
function scoreColor(s: number | null) {
  if (s == null) return "text-gray-300"
  if (s >= 80) return "text-emerald-600 font-semibold"
  if (s >= 60) return "text-amber-600 font-medium"
  return "text-red-500"
}
function srcLabel(s: string) { return s === "justjoinit" ? "JJI" : s === "nofluffjobs" ? "NF" : s === "pracuj" ? "PR" : s.slice(0, 3) }

/* ── Console ─────────────────────────────────────────────────── */
function Console({ log, running, onClear, onStop }: { log: string; running: boolean; onClear: () => void; onStop: () => void }) {
  const [open, setOpen] = useState(true)
  const ref = useRef<HTMLPreElement>(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [log])
  if (!log) return null
  return (
    <div className="bg-[#0f0f10] border-t border-[#2a2a2c]">
      <div className="flex items-center gap-2 px-3 h-7 bg-[#18181a]">
        <button onClick={() => setOpen(o => !o)} className="text-xs text-gray-500 hover:text-gray-300 w-4">{open ? "▾" : "▸"}</button>
        <span className="text-xs flex-1">{running ? <span className="text-green-500">● Running</span> : <span className="text-gray-600">Done</span>}</span>
        {running && <button onClick={onStop} className="text-xs text-red-500 hover:text-red-400">Stop</button>}
        <button onClick={onClear} className="text-xs text-gray-600 hover:text-gray-400">Clear</button>
      </div>
      {open && <pre ref={ref} className="text-xs text-green-500/70 px-3 py-2 max-h-32 overflow-auto whitespace-pre-wrap leading-5">{log}</pre>}
    </div>
  )
}

/* ── Action popover ──────────────────────────────────────────── */
const POSTED_OPTIONS = [
  { label: "All time", hours: "" }, { label: "Last 12h", hours: "12" }, { label: "Last 24h", hours: "24" },
  { label: "Last 3 days", hours: "72" }, { label: "Last week", hours: "168" },
]

function ActionPopover({ label, onRun, onClose, showMinScore }: {
  label: string; showMinScore: boolean
  onRun: (ms: number, ph: string, lang: string) => void; onClose: () => void
}) {
  const [ms, setMs] = useState(59)
  const [ph, setPh] = useState("")
  const [lang, setLang] = useState("en")
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h)
  }, [onClose])
  return (
    <div ref={ref} className="absolute top-full left-0 mt-1.5 z-30 bg-white rounded-lg border border-gray-200 shadow-xl p-3 min-w-[190px]">
      {showMinScore && (
        <label className="flex items-center gap-2 mb-3 text-xs text-gray-500">
          Min score
          <input type="number" min={0} max={100} value={ms} onChange={e => setMs(Math.max(0, Math.min(100, +e.target.value)))}
            className="w-12 h-6 text-xs text-center rounded border border-gray-200 font-medium" />
        </label>
      )}
      <p className="text-xs font-medium text-gray-400 mb-1">Posted within</p>
      <div className="flex flex-col mb-3">
        {POSTED_OPTIONS.map(o => (
          <button key={o.hours || "all"} onClick={() => setPh(o.hours)}
            className={`text-xs px-2 py-1 rounded text-left transition-colors ${ph === o.hours ? "bg-gray-100 text-gray-900 font-medium" : "text-gray-500 hover:bg-gray-50"}`}>{o.label}</button>
        ))}
      </div>
      <p className="text-xs font-medium text-gray-400 mb-1">Language</p>
      <div className="flex gap-1 mb-3">
        {[{ v: "", l: "All" }, { v: "en", l: "EN" }, { v: "pl", l: "PL" }].map(o => (
          <button key={o.v || "a"} onClick={() => setLang(o.v)}
            className={`text-xs px-2.5 py-1 rounded transition-colors ${lang === o.v ? "bg-gray-900 text-white" : "text-gray-500 hover:bg-gray-100"}`}>{o.l}</button>
        ))}
      </div>
      <button onClick={() => { onRun(ms, ph, lang); onClose() }}
        className="w-full h-7 text-xs rounded-md bg-gray-900 text-white font-medium hover:bg-gray-800 transition-colors">Run {label}</button>
    </div>
  )
}

/* ── Sidebar section ─────────────────────────────────────────── */
function Section({ title, open: defaultOpen = false, children }: { title: string; open?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-gray-100 last:border-0">
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center w-full px-3 py-2 text-left group">
        <span className={`text-[10px] mr-1.5 text-gray-400 transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">{title}</span>
      </button>
      {open && <div className="px-3 pb-2">{children}</div>}
    </div>
  )
}

/* ── Pill toggle ─────────────────────────────────────────────── */
function Pills({ items, value, onChange }: { items: { val: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map(it => (
        <button key={it.val} onClick={() => onChange(it.val)}
          className={`px-2 py-0.5 rounded text-xs transition-all
            ${value === it.val
              ? "bg-gray-900 text-white font-medium shadow-sm"
              : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"}`}>
          {it.label}
        </button>
      ))}
    </div>
  )
}

/* ── Main page ───────────────────────────────────────────────── */
export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [stats, setStats] = useState<Stats>({})
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [seniority, setSeniority] = useState("")
  const [source, setSource] = useState("")
  const [minScore, setMinScore] = useState(0)
  const [postedWithin, setPostedWithin] = useState("")
  const [language, setLanguage] = useState("en")
  const [sort, setSort] = useState<SortOpt>("fit_score")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [selected, setSelected] = useState<JobRef>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [detailWide, setDetailWide] = useState(false)
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState("")
  const [pop, setPop] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [jobUrl, setJobUrl] = useState("")

  useEffect(() => { fetch("/api/stats").then(r => r.json()).then(setStats) }, [refreshKey])
  useEffect(() => {
    const p = new URLSearchParams()
    if (status) p.set("status", status)
    if (search) p.set("search", search)
    if (source) p.set("source", source)
    if (language) p.set("language", language)
    p.set("min_score", String(minScore))
    fetch(`/api/jobs?${p}`).then(r => r.json()).then(setJobs)
  }, [status, search, source, minScore, language, refreshKey])

  function run(ep: string) {
    setLog(""); setRunning(true); setPop(null)
    const ctrl = new AbortController(); abortRef.current = ctrl
    fetch(ep, { method: "POST", signal: ctrl.signal }).then(async res => {
      const ct = res.headers.get("content-type") ?? ""
      if (ct.includes("json")) { setLog(JSON.stringify(await res.json(), null, 2)); setRunning(false); refresh(); return }
      const rdr = res.body!.getReader(); const dec = new TextDecoder()
      try { while (true) {
        const { done, value } = await rdr.read(); if (done) break
        for (const ln of dec.decode(value).split("\n").filter(l => l.startsWith("data: "))) {
          const d = ln.slice(6); if (d === "[DONE]") { setRunning(false); refresh(); return }
          setLog(p => p + d + "\n")
        }
      }} catch (e) { if ((e as Error).name !== "AbortError") throw e }
      setRunning(false)
    }).catch(e => { setLog(p => p + (e as Error).name === "AbortError" ? "\nStopped.\n" : `\nError: ${e}\n`); setRunning(false); refresh() })
  }
  function burl(base: string, ms?: number, ph?: string, lang?: string) {
    const p = new URLSearchParams()
    if (ms !== undefined) p.set("min_score", String(ms))
    if (ph) p.set("posted_within", ph)
    if (lang) p.set("language", lang)
    const q = p.toString(); return q ? `${base}?${q}` : base
  }
  function handleSort(k: SortOpt) { if (sort === k) setSortDir(d => d === "asc" ? "desc" : "asc"); else { setSort(k); setSortDir(k === "fit_score" || k === "posted_at" ? "desc" : "asc") } }
  const cutoff = postedWithin ? new Date(Date.now() - parseFloat(postedWithin) * 864e5).toISOString().slice(0, 10) : ""
  const displayed = [...jobs]
    .filter(j => !seniority || (j.seniority && j.seniority.includes(seniority)))
    .filter(j => !cutoff || (j.posted_at != null && j.posted_at >= cutoff))
    .sort((a, b) => { let c = sort === "fit_score" ? ((a.fit_score ?? -1) - (b.fit_score ?? -1)) : String(a[sort] ?? "").localeCompare(String(b[sort] ?? "")); return sortDir === "asc" ? c : -c })
  function refresh() { setRefreshKey(k => k + 1) }
  const totalAll = Object.values(stats).reduce((a, b) => a + b, 0)
  const hasFilters = status || seniority || source || minScore > 0 || postedWithin || language !== "en"

  const ab = "h-7 px-2.5 text-xs rounded-md font-medium inline-flex items-center gap-1 disabled:opacity-30 transition-colors whitespace-nowrap"

  const cols: { key?: SortOpt; label: string; w: string }[] = [
    { key: "position",  label: "Position",  w: "flex-[3] min-w-0" },
    { key: "company",   label: "Company",   w: "flex-[2] min-w-0" },
    { key: "city",      label: "City",      w: "w-28 shrink-0" },
    {                   label: "Level",     w: "w-20 shrink-0" },
    {                   label: "Salary",    w: "w-40 shrink-0" },
    { key: "fit_score", label: "Score",     w: "w-14 shrink-0 text-right" },
    {                   label: "Status",    w: "w-[72px] shrink-0" },
    {                   label: "Src",       w: "w-8 shrink-0 text-center" },
    { key: "posted_at", label: "Posted",    w: "w-20 shrink-0 text-right" },
  ]

  return (
    <div className="h-screen flex flex-col bg-[#f6f6f4]">
      {/* ─── Header ─── */}
      <header className="shrink-0 bg-white border-b border-gray-200 z-10">
        <div className="flex items-center gap-2.5 px-3 h-11">
          <button onClick={() => setSidebarOpen(o => !o)} className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16"/></svg>
          </button>
          <span className="font-semibold text-gray-900 text-sm tracking-tight">Job Tracker</span>
          <span className="text-xs text-gray-400 font-mono">{displayed.length}<span className="text-gray-300">/{totalAll}</span></span>

          <div className="flex-1 max-w-sm relative ml-1">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
            </svg>
            <input type="text" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 h-7 text-xs border border-gray-200 rounded-md bg-gray-50/80 focus:outline-none focus:ring-2 focus:ring-gray-300 focus:border-gray-300 placeholder:text-gray-400" />
          </div>

          <div className="flex items-center gap-0.5 ml-auto relative">
            <div className="relative">
              <button disabled={running} onClick={() => setPop(pop === "s" ? null : "s")} className={`${ab} text-gray-600 hover:bg-gray-100`}>Scrape ▾</button>
              {pop === "s" && (
                <div className="absolute top-full right-0 mt-1.5 z-30 bg-white rounded-lg border border-gray-200 shadow-xl py-1 min-w-[150px]">
                  {[{ l: "All platforms", p: "" }, { l: "JustJoinIT", p: "justjoinit" }, { l: "NoFluffJobs", p: "nofluffjobs" }, { l: "Pracuj.pl", p: "pracuj" }].map(o => (
                    <button key={o.p || "a"} onClick={() => { setPop(null); run(o.p ? `/api/actions/scrape?platform=${o.p}` : "/api/actions/scrape") }}
                      className="w-full text-left text-xs px-3 py-1.5 text-gray-700 hover:bg-gray-50 transition-colors">{o.l}</button>
                  ))}
                </div>
              )}
            </div>
            <div className="relative">
              <button disabled={running} onClick={() => setPop(pop === "sc" ? null : "sc")} className={`${ab} text-blue-700 hover:bg-blue-50`}>Score</button>
              {pop === "sc" && <ActionPopover label="Score" showMinScore={false} onRun={(_m, p, l) => run(burl("/api/actions/score", undefined, p, l))} onClose={() => setPop(null)} />}
            </div>
            <div className="relative">
              <button disabled={running} onClick={() => setPop(pop === "t" ? null : "t")} className={`${ab} text-violet-700 hover:bg-violet-50`}>Tailor</button>
              {pop === "t" && <ActionPopover label="Tailor" showMinScore onRun={(m, p, l) => run(burl("/api/actions/tailor", m, p, l))} onClose={() => setPop(null)} />}
            </div>
            <div className="relative">
              <button disabled={running} onClick={() => setPop(pop === "p" ? null : "p")} className={`${ab} text-amber-700 hover:bg-amber-50`}>PDFs</button>
              {pop === "p" && <ActionPopover label="PDFs" showMinScore onRun={(m, p, l) => run(burl("/api/actions/generate-pdf-batch", m, p, l))} onClose={() => setPop(null)} />}
            </div>
            <button disabled={running} onClick={() => run("/api/actions/drop-expired")} className={`${ab} text-red-600 hover:bg-red-50`}>Drop exp.</button>
            {running && <span className="text-xs text-gray-400 animate-pulse ml-1">●</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 h-8 border-t border-gray-100 bg-[#fafaf9]">
          <input type="text" placeholder="Paste any job URL (LinkedIn, Pracuj, NoFluff, etc.)"
            value={jobUrl} onChange={e => setJobUrl(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && jobUrl.trim() && !running) { run(`/api/actions/add-from-url?url=${encodeURIComponent(jobUrl.trim())}`); setJobUrl("") } }}
            className="flex-1 h-6 text-xs border border-gray-200 rounded-md px-2.5 bg-white focus:outline-none focus:ring-2 focus:ring-gray-300 placeholder:text-gray-400" />
          <button disabled={running || !jobUrl.trim()} onClick={() => { run(`/api/actions/add-from-url?url=${encodeURIComponent(jobUrl.trim())}`); setJobUrl("") }}
            className={`${ab} bg-gray-900 text-white hover:bg-gray-800 disabled:bg-gray-300`}>+ Add</button>
        </div>
        <Console log={log} running={running} onClear={() => setLog("")} onStop={() => abortRef.current?.abort()} />
      </header>

      {/* ─── Body ─── */}
      <div className="flex flex-1 min-h-0">
        {sidebarOpen && (
          <aside className="w-48 shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
            {hasFilters && <button onClick={() => { setStatus(""); setSeniority(""); setSource(""); setMinScore(0); setPostedWithin(""); setLanguage("en") }} className="text-xs text-gray-500 hover:text-gray-900 px-3 py-2 block w-full text-left border-b border-gray-100">Clear filters</button>}

            <Section title="Pipeline" open>
              {[["", "All", totalAll], ...STATUSES.map(s => [s, statusLabel(s), stats[s] ?? 0])].map(([val, label, count]) => (
                <button key={(val as string) || "all"} onClick={() => setStatus(val as string)}
                  className={`flex items-center justify-between w-full px-2 py-1 rounded text-xs transition-colors
                    ${status === val ? "bg-gray-100 text-gray-900 font-medium" : "text-gray-600 hover:bg-gray-50"}`}>
                  <span className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${val === "" ? "bg-gray-300" : STATUS_DOT[val as string] ?? "bg-gray-400"}`} />
                    {label as string}
                  </span>
                  <span className="text-[11px] font-mono text-gray-400">{count as number}</span>
                </button>
              ))}
            </Section>

            <Section title="Source">
              <Pills items={[{ val: "", label: "All" }, ...SOURCES.map(s => ({ val: s, label: srcLabel(s) }))]} value={source} onChange={setSource} />
            </Section>

            <Section title="Language" open>
              <Pills items={[{ val: "", label: "All" }, { val: "en", label: "EN" }, { val: "pl", label: "PL" }]} value={language} onChange={setLanguage} />
            </Section>

            <Section title="Posted">
              <Pills items={POSTED_FILTERS.map(f => ({ val: f.key, label: f.label }))} value={postedWithin} onChange={setPostedWithin} />
            </Section>

            <Section title="Experience">
              <Pills items={[{ val: "", label: "All" }, ...SENIORITIES.map(s => ({ val: s, label: s }))]} value={seniority} onChange={setSeniority} />
            </Section>

            <Section title="Min Score">
              <Pills items={[{ val: "0", label: "Any" }, { val: "60", label: "60+" }, { val: "70", label: "70+" }, { val: "80", label: "80+" }]}
                value={String(minScore)} onChange={v => setMinScore(+v)} />
            </Section>
          </aside>
        )}

        {/* ─── Table ─── */}
        <main className="flex-1 min-w-0 flex flex-col bg-white">
          <div className="flex items-center px-3 h-8 border-b border-gray-200 bg-[#fafaf9] shrink-0">
            {cols.map(c => (
              <div key={c.label} onClick={() => c.key && handleSort(c.key)}
                className={`${c.w} px-2 text-[11px] font-semibold text-gray-400 uppercase tracking-wide select-none ${c.key ? "cursor-pointer hover:text-gray-600" : ""}`}>
                {c.label}{c.key && sort === c.key ? <span className="ml-0.5 text-gray-600">{sortDir === "desc" ? "↓" : "↑"}</span> : ""}
              </div>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto">
            {displayed.slice(0, 200).map(job => {
              const sel = selected?.id === job.id && selected?.source === job.source
              return (
                <div key={`${job.id}-${job.source}`}
                  onClick={() => setSelected(s => { const n = s?.id === job.id && s?.source === job.source ? null : { id: job.id, source: job.source }; if (!n) setDetailWide(false); return n })}
                  className={`flex items-center px-3 h-[34px] border-b border-gray-50 cursor-pointer transition-colors
                    ${sel ? "bg-gray-100 border-l-[3px] border-l-gray-900" : `hover:bg-gray-50/80 ${STATUS_ROW[job.status] ?? ""}`}`}>
                  <div className="flex-[3] min-w-0 px-2 truncate font-medium text-gray-900">{job.position}</div>
                  <div className="flex-[2] min-w-0 px-2 text-gray-600 truncate">{job.company}</div>
                  <div className="w-28 shrink-0 px-2 text-gray-500 truncate text-xs">{job.city ?? "—"}</div>
                  <div className="w-20 shrink-0 px-2 text-gray-500 truncate text-xs">{job.seniority || "—"}</div>
                  <div className="w-40 shrink-0 px-2 truncate">{job.salary && job.salary !== "Not disclosed" ? <span className="text-emerald-700 text-xs">{job.salary}</span> : <span className="text-gray-300">—</span>}</div>
                  <div className="w-14 shrink-0 px-2 text-right"><span className={`font-mono text-xs ${scoreColor(job.fit_score)}`}>{job.fit_score ?? "—"}</span></div>
                  <div className="w-[72px] shrink-0 px-2 flex items-center gap-1.5">
                    <span className={`w-[6px] h-[6px] rounded-full ${STATUS_DOT[job.status] ?? "bg-gray-400"}`} />
                    <span className="text-xs text-gray-500">{statusLabel(job.status)}</span>
                  </div>
                  <div className="w-8 shrink-0 text-center text-[11px] text-gray-400 font-medium">{srcLabel(job.source)}</div>
                  <div className="w-20 shrink-0 px-2 text-right text-xs text-gray-400 font-mono">{job.posted_at?.slice(5) ?? "—"}</div>
                </div>
              )
            })}
            {displayed.length > 200 && <div className="text-center py-3 text-xs text-gray-400">Showing 200 of {displayed.length} — use filters to narrow</div>}
            {!displayed.length && <div className="text-center py-20 text-gray-400 text-sm">No jobs match your filters</div>}
          </div>
        </main>

        {selected && (
          <div className={`shrink-0 border-l border-gray-200 bg-white overflow-hidden transition-all ${detailWide ? "w-[55vw] min-w-[700px] max-w-[1000px]" : "w-[400px]"}`}>
            <JobDetail jobRef={selected} onClose={() => { setSelected(null); setDetailWide(false) }} onUpdated={refresh} onJobLoaded={cv => setDetailWide(cv)} />
          </div>
        )}
      </div>
    </div>
  )
}
