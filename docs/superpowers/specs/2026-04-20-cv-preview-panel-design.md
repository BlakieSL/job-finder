# CV Preview Panel with Keyword Highlighting

## Problem

When reviewing a job, the user must manually compare the tailored CV against job requirements. There is no visual way to confirm which keywords the CV covers.

## Solution

Expand the job detail panel into a two-column layout. Left column shows vacancy info (existing). Right column renders the tailored CV with requirement keywords highlighted in color.

## Layout

- Current `JobDetail` panel widens from 400px to `55vw` (clamped `min-w-[700px] max-w-[1000px]`) when `tailored_cv` is present.
- When `tailored_cv` is null, panel stays at 400px single-column (current behavior unchanged).
- Inside the expanded panel, a horizontal split using `grid grid-cols-2 gap-4`:
  - **Left column**: score, salary, status, requirements tags, fit notes, job description, notes editor, actions — same content as today, scrollable independently.
  - **Right column**: rendered tailored CV with keyword highlights, scrollable independently.

**Files modified:** Both `JobDetail.tsx` (content/rendering) and `JobsPage.tsx` (panel container width). `JobsPage.tsx` must make the panel container width dynamic — 400px when no `tailored_cv`, wider when present. `JobDetail` receives a new prop `hasTailoredCv` or the parent reads from the fetched job data to set width accordingly. Simplest approach: `JobDetail` always renders at full width of its container, and `JobsPage` controls the container width via a state variable set when the detail job data loads.

**Width communication:** `JobDetail` already fetches the full job. Add a callback prop `onJobLoaded(job)` that fires after fetch. `JobsPage` reads `job.tailored_cv` from this callback to toggle the panel width class between `w-[400px]` and `w-[55vw] min-w-[700px] max-w-[1000px]`.

## CV Parsing

`tailored_cv` arrives from the backend as a **raw JSON string** (not parsed). The frontend must `JSON.parse()` it.

**Parsed JSON structure:**

| Key          | Type   | Rendering                                      |
|--------------|--------|-------------------------------------------------|
| `title`      | string | `<h3>` heading at top of CV column              |
| `summary`    | string | Paragraph with keyword highlighting applied     |
| `skills_html`| string | Rendered via `dangerouslySetInnerHTML` with keyword highlighting applied |

**Parse failures and legacy data:** Some older records may contain non-JSON markdown text. If `JSON.parse()` throws, fall back to displaying the raw string in a `<pre>` block (current behavior) without the two-column layout. The `{error: ...}` JSON variant is also handled — if the parsed object has an `error` key, display the error message and stay single-column.

## Keyword Highlighting

**Source data:**
- `requirements_must: string[]` — must-have requirements
- `requirements_nice: string[]` — nice-to-have requirements

**Matching algorithm:**
1. Normalize each requirement to lowercase.
2. For each requirement, search the CV text for a case-insensitive substring match.
3. Wrap matched substrings in `<mark>` elements with appropriate styling.
4. Process longer requirements first to avoid partial overlap issues.

**HTML-safe highlighting for `skills_html`:** Use a temporary DOM element to walk text nodes only. Create a `<div>`, set `innerHTML`, use `TreeWalker` with `NodeFilter.SHOW_TEXT` to iterate text nodes, apply regex replacements only within text content. This avoids corrupting HTML tags or attributes. Serialize back via `innerHTML`.

For `summary` (plain text), direct regex replacement is safe.

**Colors:**
- Must-have match: `bg-emerald-100 text-emerald-800 rounded px-0.5` (green)
- Nice-to-have match: `bg-sky-100 text-sky-700 rounded px-0.5` (blue)

These colors are intentionally different from the requirement tag colors (violet/gray) used in the left column, to visually distinguish "these are the requirements" from "these matched in the CV."

**Legend:** A small inline legend above the CV column:
- `● must-have` (emerald) · `● nice-to-have` (sky blue)

## Component Structure

```
JobsPage (modified — dynamic panel width)
└── JobDetail (modified — two-column layout + CV rendering)
    ├── Header (unchanged)
    ├── ContentArea
    │   ├── when no valid tailored_cv JSON: single column (unchanged)
    │   └── when valid tailored_cv JSON: grid grid-cols-2
    │       ├── LeftColumn (vacancy info — existing content)
    │       └── RightColumn (new)
    │           ├── Legend
    │           ├── CV Title
    │           ├── CV Summary (highlighted)
    │           └── CV Skills (highlighted HTML)
    └── Footer actions (unchanged)
```

## Highlight Utility

```typescript
function highlightKeywords(
  text: string,
  mustHave: string[],
  niceToHave: string[],
  isHtml: boolean
): string
```

- Returns HTML string with `<mark class="...">` wrappers around matched keywords.
- Sorts keywords by length (longest first) to prevent partial matches.
- Escapes regex special characters in keywords.
- When `isHtml` is true, uses DOM TreeWalker to only modify text nodes.
- When `isHtml` is false, applies regex directly on plain text.

**Security note:** All HTML injected via `dangerouslySetInnerHTML` originates from the application's own pipeline (LLM-generated `skills_html`), not from user input. XSS risk is minimal and acceptable here.

## Responsive Behavior

- Panel width: `55vw` with min 700px, max 1000px.
- Each column scrolls independently via `overflow-y-auto`.
- On viewports where the panel would be < 700px, use a media query `@media (max-width: 1400px)` to stack columns vertically instead of side-by-side (`grid-cols-1` instead of `grid-cols-2`).

## No Backend Changes

The detail endpoint `GET /jobs/{id}/{source}` already returns all needed fields: `tailored_cv`, `requirements_must`, `requirements_nice`.

## Bugfix alongside

Add missing `tailored` status to the status dropdown in `JobDetail.tsx` (line 225). Currently lists `["new", "scored", "pdf_ready", "applied", "expired"]` but omits `tailored`, which is the status set when a CV is tailored.

## Edge Cases

- `tailored_cv` is null → single column, no change.
- `tailored_cv` fails `JSON.parse()` (legacy markdown) → show raw text in `<pre>`, single column.
- `tailored_cv` parses to `{error: ...}` → show error message, single column.
- Requirements arrays are empty → CV renders without highlights.
- A keyword appears multiple times → all occurrences highlighted.
- Keywords that are substrings of other keywords → longer keywords matched first, shorter ones skip already-wrapped regions.
