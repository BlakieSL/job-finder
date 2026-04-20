# CV Preview Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-column detail panel that shows the tailored CV alongside vacancy info, with requirement keywords highlighted in green (must-have) and blue (nice-to-have).

**Architecture:** Modify `JobDetail.tsx` to parse `tailored_cv` JSON and render a two-column grid when valid CV data exists. Add a `highlightKeywords` utility using DOM TreeWalker for HTML-safe highlighting. Modify `JobsPage.tsx` to dynamically size the detail panel container based on whether the selected job has a tailored CV.

**Tech Stack:** React 19, Tailwind CSS 4, TypeScript

**Spec:** `docs/superpowers/specs/2026-04-20-cv-preview-panel-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `dashboard/frontend/src/pages/JobDetail.tsx` | Modify | CV parsing, two-column layout, highlight utility, CV rendering |
| `dashboard/frontend/src/pages/JobsPage.tsx` | Modify | Dynamic panel width based on `onJobLoaded` callback |

---

### Task 1: Add `highlightKeywords` utility to JobDetail.tsx

**Files:**
- Modify: `dashboard/frontend/src/pages/JobDetail.tsx:1-4` (add utility before component)

- [ ] **Step 1: Add the `highlightKeywords` function at the top of JobDetail.tsx, after imports**

Insert after line 4 (`type JobRef = ...`), before the `FullJob` type:

```typescript
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
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd dashboard/frontend && npx tsc --noEmit`
Expected: No new errors from the utility function.

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/JobDetail.tsx
git commit -m "feat: add highlightKeywords utility to JobDetail"
```

---

### Task 2: Parse tailored_cv JSON and add two-column layout to JobDetail

**Files:**
- Modify: `dashboard/frontend/src/pages/JobDetail.tsx:6-13` (FullJob type — no change needed, already has `tailored_cv: string | null`)
- Modify: `dashboard/frontend/src/pages/JobDetail.tsx:29-269` (component body)

- [ ] **Step 1: Add a `TailoredCv` type and a `parseTailoredCv` helper after the `highlightKeywords` function**

```typescript
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
```

- [ ] **Step 2: Add `onJobLoaded` callback prop and wire it up**

Update the component signature at line 29 from:

```typescript
export function JobDetail({ jobRef, onClose, onUpdated }: {
  jobRef: JobRef; onClose: () => void; onUpdated: () => void
}) {
```

to:

```typescript
export function JobDetail({ jobRef, onClose, onUpdated, onJobLoaded }: {
  jobRef: JobRef; onClose: () => void; onUpdated: () => void
  onJobLoaded?: (hasValidCv: boolean) => void
}) {
```

In the existing `useEffect` fetch (line 38-44), after `setJob(j)`, add the callback:

```typescript
.then(j => {
  setJob(j); setNotes(j.notes ?? ""); setActionLog("")
  onJobLoaded?.(parseTailoredCv(j.tailored_cv) !== null)
})
```

- [ ] **Step 3: Replace the content area with a two-column layout when CV data is present**

Replace the existing `<div className="overflow-y-auto flex-1 flex flex-col gap-4 p-4">` block (lines 124-260) with:

```tsx
{job && (() => {
  const cvData = parseTailoredCv(job.tailored_cv)
  const mustHave = job.requirements_must ?? []
  const niceToHave = job.requirements_nice ?? []

  return cvData ? (
    // ── Two-column layout ──
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
            <a href={`/api/jobs/${job.id}/${job.source}/pdf`} target="_blank" rel="noreferrer"
              className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium hover:bg-amber-100 flex items-center gap-0.5">
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
          <textarea value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Add notes..."
            className="w-full mt-1.5 text-sm rounded-lg border border-gray-200 p-2.5 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
          />
          <Button size="sm" onClick={saveNotes} className="mt-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs h-7">
            Save notes
          </Button>
        </div>

        {/* Status + PDF actions */}
        <div className="border-t border-gray-100 pt-3 flex flex-wrap gap-2 items-center">
          <select key={job.id + job.status} defaultValue={job.status}
            onChange={e => changeStatus(e.target.value)}
            className="h-7 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-400">
            {["new", "scored", "tailored", "pdf_ready", "applied", "expired"].map(s =>
              <option key={s} value={s}>{s === "pdf_ready" ? "PDF ready" : s}</option>
            )}
          </select>
          <Button size="sm" variant="outline" disabled={running}
            onClick={() => runActionPost(`/api/actions/generate-pdf/${job.id}/${job.source}`)}
            className="h-7 text-xs border-amber-200 text-amber-700 hover:bg-amber-50">
            {pdfExists ? "Re-render PDF" : "Generate PDF"}
          </Button>
          {pdfExists && (
            <a href={`/api/jobs/${job.id}/${job.source}/pdf`} target="_blank" rel="noreferrer"
              className="inline-flex items-center h-7 px-3 text-xs rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 font-medium transition-colors">
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
    // ── Single column (no valid CV data) ──
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
          <a href={`/api/jobs/${job.id}/${job.source}/pdf`} target="_blank" rel="noreferrer"
            className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium hover:bg-amber-100 flex items-center gap-0.5">
            📄 PDF ↗
          </a>
        )}
      </div>

      {/* Fit notes */}
      {job.fit_notes && (
        <p className="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 leading-relaxed">{job.fit_notes}</p>
      )}

      {/* Requirements */}
      {((job.requirements_must?.length ?? 0) + (job.requirements_nice?.length ?? 0)) > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {(job.requirements_must ?? []).map(r => (
            <span key={r} className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 font-medium">{r}</span>
          ))}
          {(job.requirements_nice ?? []).map(r => (
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

      {/* Tailored CV raw fallback */}
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
        <textarea value={notes} onChange={e => setNotes(e.target.value)}
          placeholder="Add notes..."
          className="w-full mt-1.5 text-sm rounded-lg border border-gray-200 p-2.5 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
        />
        <Button size="sm" onClick={saveNotes} className="mt-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs h-7">
          Save notes
        </Button>
      </div>

      {/* Status + PDF actions */}
      <div className="border-t border-gray-100 pt-3 flex flex-wrap gap-2 items-center">
        <select key={job.id + job.status} defaultValue={job.status}
          onChange={e => changeStatus(e.target.value)}
          className="h-7 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-400">
          {["new", "scored", "tailored", "pdf_ready", "applied", "expired"].map(s =>
            <option key={s} value={s}>{s === "pdf_ready" ? "PDF ready" : s}</option>
          )}
        </select>
        {job.tailored_cv && (
          <Button size="sm" variant="outline" disabled={running}
            onClick={() => runActionPost(`/api/actions/generate-pdf/${job.id}/${job.source}`)}
            className="h-7 text-xs border-amber-200 text-amber-700 hover:bg-amber-50">
            {pdfExists ? "Re-render PDF" : "Generate PDF"}
          </Button>
        )}
        {pdfExists && (
          <a href={`/api/jobs/${job.id}/${job.source}/pdf`} target="_blank" rel="noreferrer"
            className="inline-flex items-center h-7 px-3 text-xs rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 font-medium transition-colors">
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
```

Note: the `tailored` status is now included in the dropdown `["new", "scored", "tailored", "pdf_ready", "applied", "expired"]` — this fixes the pre-existing bug.

- [ ] **Step 4: Verify no syntax errors**

Run: `cd dashboard/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/frontend/src/pages/JobDetail.tsx
git commit -m "feat: two-column CV preview with keyword highlighting in JobDetail"
```

---

### Task 3: Dynamic panel width in JobsPage.tsx

**Files:**
- Modify: `dashboard/frontend/src/pages/JobsPage.tsx:529,605-611`

- [ ] **Step 1: Add state for panel width and pass callback to JobDetail**

In `JobsPage` component (line 518), add state after line 531 (`sidebarOpen`):

```typescript
const [detailWide, setDetailWide] = useState(false)
```

- [ ] **Step 2: Update the detail panel container (lines 605-611)**

Replace:

```tsx
{selected && (
  <div className="w-[400px] shrink-0 py-5">
    <div className="sticky top-20">
      <JobDetail jobRef={selected} onClose={() => setSelected(null)} onUpdated={refresh} />
    </div>
  </div>
)}
```

With:

```tsx
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
```

The `onJobLoaded` prop was defined with a `boolean` signature in Task 2 — `JobDetail` calls `onJobLoaded?.(parseTailoredCv(j.tailored_cv) !== null)` in its fetch handler. `JobsPage` simply passes the boolean to `setDetailWide`.

- [ ] **Step 3: Reset `detailWide` when selection changes**

In the `setSelected` toggle (line 594), also reset:

```typescript
onClick={() => setSelected(sel => {
  const next = sel?.id === job.id && sel?.source === job.source ? null : { id: job.id, source: job.source }
  if (!next) setDetailWide(false)
  return next
})}
```

- [ ] **Step 4: Verify no syntax errors**

Run: `cd dashboard/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/frontend/src/pages/JobDetail.tsx dashboard/frontend/src/pages/JobsPage.tsx
git commit -m "feat: dynamic detail panel width for CV preview"
```

---

### Task 4: Visual verification in browser

- [ ] **Step 1: Start the dev server**

```bash
cd dashboard/frontend && npm run dev
```

- [ ] **Step 2: Test with a job that has a tailored CV**

1. Open the app in browser
2. Filter to `tailored` or `pdf_ready` status
3. Click a job — panel should expand to ~55vw with two columns
4. Left column: vacancy info with requirements tags, job description, notes
5. Right column: CV title, highlighted summary, highlighted skills
6. Green highlights on must-have matches, blue on nice-to-have matches
7. Legend shows above the CV

- [ ] **Step 3: Test with a job that has no tailored CV**

1. Filter to `new` or `scored` status
2. Click a job — panel should stay at 400px, single column
3. All existing functionality unchanged

- [ ] **Step 4: Test edge cases**

1. Switch between a tailored and non-tailored job — panel should smoothly resize
2. Close the panel — it should reset width
3. If any job has legacy markdown in `tailored_cv`, it should show raw text in single column

- [ ] **Step 5: Final commit if any adjustments needed**

```bash
git add -u
git commit -m "fix: visual adjustments to CV preview panel"
```
