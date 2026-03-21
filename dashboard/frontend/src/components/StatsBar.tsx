import { useEffect, useState } from "react"

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  new:       { bg: "bg-gray-100 border border-gray-200",   text: "text-gray-700",   label: "New" },
  scored:    { bg: "bg-blue-50 border border-blue-200",    text: "text-blue-700",   label: "Scored" },
  pdf_ready: { bg: "bg-amber-50 border border-amber-200",  text: "text-amber-700",  label: "PDF Ready" },
  applied:   { bg: "bg-green-50 border border-green-200",  text: "text-green-700",  label: "Applied" },
  expired:   { bg: "bg-red-50 border border-red-200",      text: "text-red-700",    label: "Expired" },
}

export function StatsBar() {
  const [stats, setStats] = useState<Record<string, number>>({})

  useEffect(() => {
    fetch("/api/stats").then(r => r.json()).then(setStats)
  }, [])

  const order = ["scored", "pdf_ready", "applied", "expired", "new"]
  const sorted = order.filter(s => s in stats).concat(Object.keys(stats).filter(s => !order.includes(s)))

  return (
    <div className="flex gap-3 px-6 py-4 flex-wrap border-b border-border bg-gray-50/50">
      {sorted.map(status => {
        const style = STATUS_STYLES[status] ?? { bg: "bg-gray-100 border border-gray-200", text: "text-gray-700", label: status }
        return (
          <div key={status} className={`rounded-md px-4 py-2 flex items-center gap-3 ${style.bg}`}>
            <span className={`text-2xl font-bold ${style.text}`}>{stats[status]}</span>
            <span className={`text-xs font-medium uppercase tracking-wide ${style.text} opacity-70`}>{style.label}</span>
          </div>
        )
      })}
    </div>
  )
}
