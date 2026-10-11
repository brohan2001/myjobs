# myjobs Feed Frontend

Production feed frontend implementing design direction **C "Field notes"** from the design brief.
Built with Next.js 15 (App Router), TypeScript, and self-hosted Atkinson Hyperlegible typography.

## Features

- **Direction C: Field Notes**: Calm, humanist typography (Atkinson Hyperlegible), natural earth tone palette with WCAG AA contrast, generous density, no generic cards or gradients.
- **Server-rendered feed**: Initial paint renders on the server. Filter state lives in URL query params for shareable links.
- **Sentence-style filters**: Natural language controls (`Showing [work mode] jobs [place] from the [posted within]. Pay shown [currency].`).
- **Time bucket grouping**: Rows grouped by freshness (`last hour`, `earlier today`, `yesterday`, `this week`, `older`).
- **New since last visit**: Visual divider highlighting postings added since your last visit using `localStorage`.
- **Currency switch**: Display salaries as posted (native), or converted to INR (LPA) / USD, saved to `localStorage`.
- **Keyboard navigation**:
  - `j` / `k`: Move focus between job postings
  - `Enter`: Open the focused job in a new tab
  - `/`: Focus search input
  - `Esc`: Unfocus search
- **Light & Dark themes**: System default with a manual toggle stored in `localStorage`.
- **Job detail page**: `/jobs/[id]` renders full sanitized job description with "Apply on company site" link.

## Running Locally

### Development

```bash
cd web
npm install
API_ORIGIN=http://127.0.0.1:8090 npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Production Build

```bash
cd web
npm run build
npm start
```

### Running Tests

Run the format contract tests:

```bash
cd web
npx vitest run
```

### Type Checking

```bash
cd web
npx tsc --noEmit
```
