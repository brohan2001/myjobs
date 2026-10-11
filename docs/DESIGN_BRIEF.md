# Design brief: the feed

## What it is
A public page where anyone can scan the newest jobs from thousands of company career sites, worldwide, with India as the
default lens. People open it like a news ticker: several times a day, often on a phone over mobile data, looking for what's new
since last time.

## Point of view
**Freshness is the product.** The most important fact about every row is *how recently it appeared*; the second is *where*.
The page should feel like a live instrument, not a marketing site. Information-dense, calm and fast. No hero, no pitch.

## Jobs the screen must do
1. Show the newest jobs first, with "how long ago" always visible.
2. Answer "what's new since I last looked?" with a clear "new since your last visit" marker (stored in localStorage).
3. Filter in one or two taps: region (India by default, with city chips that understand aliases such as Bengaluru/Bangalore and
   Gurugram/Gurgaon), work mode (remote / hybrid / onsite), posted within (1h, 24h, 3d, 7d), company, and a text search.
4. Show salary when the posting has it: INR as LPA ("₹18–24 LPA"), other currencies natively, with an optional switch to show everything in one currency.
5. Show trust: "Updated 4 min ago · 312,408 open jobs · 2,680 companies", plus the source ATS on each row.
6. Have empty, loading and error states with a human voice ("Nothing in Pune in the last hour. Try 24 hours?").

## Constraints
- Mobile-first, from 360 px up. The first meaningful paint must work on a slow 3G connection: system or one self-hosted variable font, no
  framework needed for the list, no layout shift as rows load.
- Light and dark themes. WCAG AA contrast. Full keyboard navigation (j/k to move, Enter to open, / to search).
- **Banned:** purple/blue gradients, glassmorphism, gradient hero headlines, emoji as icons, uniform rounded cards with
  drop shadows, the Inter + slate + indigo look, sparkle icons, filler marketing copy.
- **Copy:** written like a person, short, specific. No exclamation marks.

## Three directions to mock up (the feed screen only)
- **A: Ledger.** Classifieds and financial-table heritage. Paper-white and ink, one sharp accent. A serif for headlines,
  tabular numerals, hairline rules, a time column in the left gutter. Feels like reading the jobs page of a good newspaper.
- **B: Departures.** Transit-board heritage. A dark default with high-contrast amber, a monospace grid, and city codes as
  first-class chips (BLR, BOM, DEL, HYD, PNQ, MAA, SFO, LON). Rows grouped by time bucket ("last hour", "earlier today"). A light
  "platform signage" variant.
- **C: Field notes.** Warm and human. A humanist sans with excellent legibility, a muted natural palette, a generous but still
  dense list, and filters as plain-language sentences ("Showing **remote** jobs in **India** from the **last 24 hours**"), where
  each bold word is a control.

The decision criteria are scan speed on a phone, how clearly freshness reads, and distinctiveness.
