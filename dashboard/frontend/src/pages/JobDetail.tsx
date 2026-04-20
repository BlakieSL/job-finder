import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"

type JobRef = { id: string; source: string }

// ── highlight utility ────────────────────────────────────────────────────────
function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function highlightKeywords(
  text: string,
  mustHave: string[],
  niceToHave: string[],
): string {
  const tags: { pattern: RegExp; cls: string }[] = []

  const sorted = [
    ...mustHave.map(k => ({ keyword: k, cls: "bg-emerald-100 text-emerald-800 rounded px-0.5" })),
    ...niceToHave.map(k => ({ keyword: k, cls: "bg-sky-100 text-sky-700 rounded px-0.5" })),
  ].sort((a, b) => b.keyword.length - a.keyword.length)

  for (const { keyword, cls } of sorted) {
    if (!keyword.trim()) continue
    tags.push({ pattern: new RegExp(`(${escapeRegex(keyword)})`, "gi"), cls })
  }

  if (tags.length === 0) return text

  // Always use DOM TreeWalker — safe for both plain text and HTML.
  // For plain text input, the browser treats it as a single text node,
  // so this approach works identically. This avoids the re-wrapping bug
  // where sequential regex passes on a raw string would match inside
  // previously injected <mark> class attributes.
  const container = document.createElement("div")
  container.innerHTML = text
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  while (walker.nextNode()) textNodes.push(walker.currentNode as Text)

  for (const node of textNodes) {
    let html = node.textContent ?? ""
    for (const { pattern, cls } of tags) {
      html = html.replace(pattern, `<mark class="${cls}">$1</mark>`)
    }
    if (html !== node.textContent) {
      const span = document.createElement("span")
      span.innerHTML = html
      node.parentNode?.replaceChild(span, node)
    }
  }

  return container.innerHTML
}

// ── tailored CV parser ────────────────────────────────────────────────────────
type TailoredCvData = { title: string; summary: string; skills_html: string }

function parseTailoredCv(raw: string | null): TailoredCvData | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed.error) return null
    if (parsed.title && parsed.summary && parsed.skills_html) return parsed as TailoredCvData
    return null
  } catch {
    return null
  }
}

type FullJob = {
  id: string; source: string; position: string; company: string
  seniority: string; salary: string; fit_score: number | null
  fit_notes: string | null; status: string; job_description: string
  requirements_must: string[]; requirements_nice: string[]
  tailored_cv: string | null; notes: string | null
  url: string; expires_at: string
}

const STATUS_COLORS: Record<string, string> = {
  new:       "bg-gray-100 text-gray-600",
  scored:    "bg-blue-50 text-blue-700",
  tailored:  "bg-purple-50 text-purple-700",
  pdf_ready: "bg-amber-50 text-amber-700",
  applied:   "bg-green-50 text-green-700",
  expired:   "bg-red-50 text-red-600",
}

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-600"
  if (score >= 60) return "text-amber-600"
  return "text-red-500"
}

export function JobDetail({ jobRef, onClose, onUpdated, onJobLoaded }: {
  jobRef: JobRef; onClose: () => void; onUpdated: () => void
  onJobLoaded?: (hasValidCv: boolean) => void
}) {
  const [job, setJob] = useState<FullJob | null>(null)
  const [notes, setNotes] = useState("")
  const [actionLog, setActionLog] = useState("")
  const [running, setRunning] = useState(false)
  const [pdfExists, setPdfExists] = useState(false)

  useEffect(() => {
    setJob(null)
    setPdfExists(false)
    fetch(`/api/jobs/${jobRef.id}/${jobRef.source}`)
      .then(r => r.json())
      .then(j => {
        setJob(j); setNotes(j.notes ?? ""); setActionLog("")
        onJobLoaded?.(parseTailoredCv(j.tailored_cv) !== null)
      })
  }, [jobRef.id, jobRef.source])

  // Check if PDF exists whenever job loads or status changes
  useEffect(() => {
    if (!job) return
    fetch(`/api/jobs/${job.id}/${job.source}/pdf-exists`)
      .then(r => r.json())
      .then(d => setPdfExists(d.exists === true))
      .catch(() => setPdfExists(false))
  }, [job?.id, job?.source, job?.status])

  function saveNotes() {
    if (!job) return
    fetch(`/api/jobs/${job.id}/${job.source}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes })
    }).then(onUpdated)
  }

  function changeStatus(status: string) {
    if (!job) return
    fetch(`/api/jobs/${job.id}/${job.source}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    }).then(() => { onUpdated() })
  }

  function runActionPost(endpoint: string) {
    setActionLog("Running...\n")
    setRunning(true)
    fetch(endpoint, { method: "POST" }).then(async res => {
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split("\n").filter(l => l.startsWith("data: "))) {
          const data = line.slice(6)
          if (data === "[DONE]") {
            setRunning(false)
            onUpdated()
            // Re-check PDF existence after generation completes
            if (job) {
              fetch(`/api/jobs/${job.id}/${job.source}/pdf-exists`)
                .then(r => r.json())
                .then(d => setPdfExists(d.exists === true))
                .catch(() => {})
            }
            return
          }
          setActionLog(prev => prev + data + "\n")
        }
      }
      setRunning(false)
    }).catch(() => setRunning(false))
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col max-h-[calc(100vh-96px)]">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-gray-100">
        <div className="flex-1 min-w-0">
          {job ? (
            <>
              <h2 className="font-semibold text-gray-900 text-sm leading-snug">{job.position}</h2>
              <p className="text-xs text-gray-500 mt-0.5">{job.company} · {job.seniority}</p>
            </>
          ) : (
            <div className="h-8 bg-gray-100 rounded animate-pulse" />
          )}
        </div>
        <button onClick={onClose} className="ml-3 text-gray-400 hover:text-gray-600 shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>

      {job && (() => {
        const cvData = parseTailoredCv(job.tailored_cv)
        const mustHave = job.requirements_must ?? []
        const niceToHave = job.requirements_nice ?? []

        return cvData ? (
          <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-2 gap-0">
            {/* Left: vacancy info */}
            <div className="overflow-y-auto flex flex-col gap-4 p-4 border-r border-gray-100">

              {/* Score + salary + status + links */}
              <div className="flex items-center gap-3 flex-wrap">
                {job.fit_score != null && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-gray-400">Fit</span>
                    <span className={`text-lg font-bold ${scoreColor(job.fit_score)}`}>{job.fit_score}</span>
                  </div>
                )}
                {job.salary && job.salary !== "Not disclosed" && (
                  <span className="text-sm font-semibold text-emerald-600">{job.salary}</span>
                )}
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ml-auto ${STATUS_COLORS[job.status] ?? "bg-gray-100 text-gray-600"}`}>
                  {job.status === "pdf_ready" ? "PDF ready" : job.status}
                </span>
                <a href={job.url} target="_blank" rel="noreferrer"
                  className="text-xs text-violet-600 hover:underline flex items-center gap-0.5">
                  View ↗
                </a>
                {pdfExists && (
                  <a
                    href={`/api/jobs/${job.id}/${job.source}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium hover:bg-amber-100 flex items-center gap-0.5"
                  >
                    📄 PDF ↗
                  </a>
                )}
              </div>

              {/* Fit notes */}
              {job.fit_notes && (
                <p className="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 leading-relaxed">{job.fit_notes}</p>
              )}

              {/* Requirements */}
              {(mustHave.length + niceToHave.length) > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {mustHave.map(r => (
                    <span key={r} className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 font-medium">{r}</span>
                  ))}
                  {niceToHave.map(r => (
                    <span key={r} className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-200">{r}</span>
                  ))}
                </div>
              )}

              {/* Job description */}
              {job.job_description && (
                <details open className="group">
                  <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-700 select-none flex items-center gap-1">
                    <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
                    </svg>
                    Job Description
                  </summary>
                  <div className="mt-2 text-xs text-gray-600 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                    {job.job_description}
                  </div>
                </details>
              )}

              {/* Notes */}
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Notes</label>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Add notes..."
                  className="w-full mt-1.5 text-sm rounded-lg border border-gray-200 p-2.5 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
                />
                <Button size="sm" onClick={saveNotes} className="mt-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs h-7">
                  Save notes
                </Button>
              </div>

              {/* Status + PDF actions */}
              <div className="border-t border-gray-100 pt-3 flex flex-wrap gap-2 items-center">
                <select
                  key={job.id + job.status}
                  defaultValue={job.status}
                  onChange={e => changeStatus(e.target.value)}
                  className="h-7 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
                >
                  {["new", "scored", "tailored", "pdf_ready", "applied", "expired"].map(s =>
                    <option key={s} value={s}>{s === "pdf_ready" ? "PDF ready" : s}</option>
                  )}
                </select>
                <Button
                  size="sm" variant="outline" disabled={running}
                  onClick={() => runActionPost(`/api/actions/generate-pdf/${job.id}/${job.source}`)}
                  className="h-7 text-xs border-amber-200 text-amber-700 hover:bg-amber-50"
                >
                  {pdfExists ? "Re-render PDF" : "Generate PDF"}
                </Button>
                {pdfExists && (
                  <a
                    href={`/api/jobs/${job.id}/${job.source}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center h-7 px-3 text-xs rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 font-medium transition-colors"
                  >
                    Open PDF ↗
                  </a>
                )}
              </div>

              {/* Action log */}
              {actionLog && (
                <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 max-h-36 overflow-auto font-mono whitespace-pre-wrap">
                  {actionLog}
                </pre>
              )}
            </div>

            {/* Right: tailored CV */}
            <div className="overflow-y-auto p-4 flex flex-col gap-3">
              {/* Legend */}
              <div className="flex items-center gap-3 text-xs text-gray-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" /> must-have</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-sky-400" /> nice-to-have</span>
              </div>

              <h3 className="text-base font-bold text-gray-900">{cvData.title}</h3>

              <div className="text-sm text-gray-700 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: highlightKeywords(cvData.summary, mustHave, niceToHave) }} />

              <hr className="border-gray-100" />

              <div className="text-sm text-gray-700 leading-relaxed [&_span]:inline"
                dangerouslySetInnerHTML={{ __html: highlightKeywords(cvData.skills_html, mustHave, niceToHave) }} />
            </div>
          </div>
        ) : (
          <div className="overflow-y-auto flex-1 flex flex-col gap-4 p-4">

            {/* Score + salary + status + links */}
            <div className="flex items-center gap-3 flex-wrap">
              {job.fit_score != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-400">Fit</span>
                  <span className={`text-lg font-bold ${scoreColor(job.fit_score)}`}>{job.fit_score}</span>
                </div>
              )}
              {job.salary && job.salary !== "Not disclosed" && (
                <span className="text-sm font-semibold text-emerald-600">{job.salary}</span>
              )}
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ml-auto ${STATUS_COLORS[job.status] ?? "bg-gray-100 text-gray-600"}`}>
                {job.status === "pdf_ready" ? "PDF ready" : job.status}
              </span>
              <a href={job.url} target="_blank" rel="noreferrer"
                className="text-xs text-violet-600 hover:underline flex items-center gap-0.5">
                View ↗
              </a>
              {pdfExists && (
                <a
                  href={`/api/jobs/${job.id}/${job.source}/pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium hover:bg-amber-100 flex items-center gap-0.5"
                >
                  📄 PDF ↗
                </a>
              )}
            </div>

            {/* Fit notes */}
            {job.fit_notes && (
              <p className="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 leading-relaxed">{job.fit_notes}</p>
            )}

            {/* Requirements */}
            {(mustHave.length + niceToHave.length) > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {mustHave.map(r => (
                  <span key={r} className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 font-medium">{r}</span>
                ))}
                {niceToHave.map(r => (
                  <span key={r} className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-200">{r}</span>
                ))}
              </div>
            )}

            {/* Job description */}
            {job.job_description && (
              <details open className="group">
                <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-700 select-none flex items-center gap-1">
                  <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
                  </svg>
                  Job Description
                </summary>
                <div className="mt-2 text-xs text-gray-600 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                  {job.job_description}
                </div>
              </details>
            )}

            {/* Tailored CV (raw, collapsible — only shown when not valid JSON) */}
            {job.tailored_cv && (
              <details className="group">
                <summary className="text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-700 select-none flex items-center gap-1">
                  <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
                  </svg>
                  Tailored CV
                </summary>
                <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap font-mono bg-gray-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                  {job.tailored_cv}
                </pre>
              </details>
            )}

            {/* Notes */}
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Notes</label>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Add notes..."
                className="w-full mt-1.5 text-sm rounded-lg border border-gray-200 p-2.5 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
              />
              <Button size="sm" onClick={saveNotes} className="mt-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs h-7">
                Save notes
              </Button>
            </div>

            {/* Status + PDF actions */}
            <div className="border-t border-gray-100 pt-3 flex flex-wrap gap-2 items-center">
              <select
                key={job.id + job.status}
                defaultValue={job.status}
                onChange={e => changeStatus(e.target.value)}
                className="h-7 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                {["new", "scored", "tailored", "pdf_ready", "applied", "expired"].map(s =>
                  <option key={s} value={s}>{s === "pdf_ready" ? "PDF ready" : s}</option>
                )}
              </select>
              {job.tailored_cv && (
                <Button
                  size="sm" variant="outline" disabled={running}
                  onClick={() => runActionPost(`/api/actions/generate-pdf/${job.id}/${job.source}`)}
                  className="h-7 text-xs border-amber-200 text-amber-700 hover:bg-amber-50"
                >
                  {pdfExists ? "Re-render PDF" : "Generate PDF"}
                </Button>
              )}
              {pdfExists && (
                <a
                  href={`/api/jobs/${job.id}/${job.source}/pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center h-7 px-3 text-xs rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 font-medium transition-colors"
                >
                  Open PDF ↗
                </a>
              )}
              {!job.tailored_cv && (
                <span className="text-xs text-gray-400 italic">No tailored CV yet — use "Tailor all" in the pipeline bar</span>
              )}
            </div>

            {/* Action log */}
            {actionLog && (
              <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 max-h-36 overflow-auto font-mono whitespace-pre-wrap">
                {actionLog}
              </pre>
            )}
          </div>
        )
      })()}

      {!job && (
        <div className="p-4 flex flex-col gap-3">
          {[1,2,3].map(i => <div key={i} className="h-4 bg-gray-100 rounded animate-pulse" />)}
        </div>
      )}
    </div>
  )
}
