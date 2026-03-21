import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"

// GitHub-style status pill colors
const STATUS_STYLES: Record<string, string> = {
  new:       "bg-gray-100 text-gray-600 border border-gray-200",
  scored:    "bg-blue-50 text-blue-700 border border-blue-200",
  pdf_ready: "bg-amber-50 text-amber-700 border border-amber-200",
  applied:   "bg-green-50 text-green-700 border border-green-200",
  expired:   "bg-red-50 text-red-600 border border-red-200",
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600 border border-gray-200"}`}>
      {status}
    </span>
  )
}

function ScoreCell({ score }: { score: number | null }) {
  if (score === null || score === undefined) return <span className="text-gray-400">—</span>
  const color = score >= 80 ? "text-green-700 font-semibold" : score >= 60 ? "text-amber-700 font-semibold" : "text-red-600 font-semibold"
  return <span className={color}>{score}</span>
}

type Job = {
  id: string
  source: string
  position: string
  company: string
  seniority: string
  salary: string
  fit_score: number | null
  status: string
  expires_at: string
  url: string
}

type SortKey = "position" | "company" | "seniority" | "fit_score" | "status" | "expires_at"
type SortDir = "asc" | "desc"

function sortJobs(jobs: Job[], key: SortKey, dir: SortDir): Job[] {
  return [...jobs].sort((a, b) => {
    const av = a[key] ?? ""
    const bv = b[key] ?? ""
    let cmp = 0
    if (key === "fit_score") {
      cmp = ((a.fit_score ?? -1) - (b.fit_score ?? -1))
    } else {
      cmp = String(av).localeCompare(String(bv))
    }
    return dir === "asc" ? cmp : -cmp
  })
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-gray-600">{dir === "asc" ? "↑" : "↓"}</span>
}

export function JobsTable({ onSelect, refreshKey }: {
  onSelect: (job: Job) => void
  refreshKey: number
}) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [minScore, setMinScore] = useState(0)
  const [sortKey, setSortKey] = useState<SortKey>("fit_score")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  useEffect(() => {
    const params = new URLSearchParams()
    if (status) params.set("status", status)
    if (search) params.set("search", search)
    params.set("min_score", String(minScore))
    fetch(`/api/jobs?${params}`).then(r => r.json()).then(setJobs)
  }, [status, search, minScore, refreshKey])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc")
    } else {
      setSortKey(key)
      setSortDir(key === "fit_score" ? "desc" : "asc")
    }
  }

  const sorted = sortJobs(jobs, sortKey, sortDir)

  const columns: { label: string; key?: SortKey; className?: string }[] = [
    { label: "Position", key: "position" },
    { label: "Company",  key: "company" },
    { label: "Seniority",key: "seniority" },
    { label: "Salary" },
    { label: "Score",    key: "fit_score" },
    { label: "Status",   key: "status" },
    { label: "Expires",  key: "expires_at" },
    { label: "" },
  ]

  return (
    <div className="flex flex-col">
      {/* Filter bar */}
      <div className="flex gap-3 items-center flex-wrap px-6 py-3 border-b border-border bg-white">
        <Input
          placeholder="Search position or company..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-72 h-8 text-sm"
        />
        <select
          value={status}
          onChange={e => setStatus(e.target.value)}
          className="h-8 rounded-md border border-input bg-white px-3 text-sm text-gray-700"
        >
          <option value="">All statuses</option>
          {["new", "scored", "pdf_ready", "applied", "expired"].map(s =>
            <option key={s} value={s}>{s}</option>
          )}
        </select>
        <label className="text-sm text-gray-500 flex items-center gap-2">
          Min score: <span className="font-semibold text-gray-700 w-6 text-center">{minScore}</span>
          <input
            type="range" min={0} max={100} value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            className="w-28 accent-blue-600"
          />
        </label>
        <span className="text-sm text-gray-400 ml-auto">{jobs.length} jobs</span>
      </div>

      {/* Table */}
      <div className="overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left">
              {columns.map(col => (
                <th
                  key={col.label}
                  className={`py-2 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap select-none ${col.key ? "cursor-pointer hover:text-gray-700" : ""}`}
                  onClick={() => col.key && toggleSort(col.key)}
                >
                  {col.label}
                  {col.key && <SortIcon active={sortKey === col.key} dir={sortDir} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map(job => (
              <tr
                key={`${job.id}-${job.source}`}
                className="bg-white hover:bg-blue-50/40 cursor-pointer transition-colors"
                onClick={() => onSelect(job)}
              >
                <td className="py-2.5 px-4 font-medium text-gray-900 max-w-xs">
                  <span className="line-clamp-1">{job.position}</span>
                </td>
                <td className="py-2.5 px-4 text-gray-700 whitespace-nowrap">{job.company}</td>
                <td className="py-2.5 px-4 text-gray-500">{job.seniority}</td>
                <td className="py-2.5 px-4 text-gray-400 text-xs max-w-[140px]">
                  <span className="line-clamp-1">{job.salary}</span>
                </td>
                <td className="py-2.5 px-4"><ScoreCell score={job.fit_score} /></td>
                <td className="py-2.5 px-4"><StatusPill status={job.status} /></td>
                <td className="py-2.5 px-4 text-gray-400 text-xs">{job.expires_at}</td>
                <td className="py-2.5 px-4">
                  <button
                    className="text-gray-400 hover:text-blue-600 transition-colors text-base"
                    onClick={e => { e.stopPropagation(); window.open(job.url, "_blank") }}
                    title="Open job posting"
                  >
                    ↗
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
