"use client";

import { useMemo } from "react";
import { Job } from "@/lib/types";

interface SidebarNotesProps {
  jobs: Job[];
}

export function SidebarNotes({ jobs }: SidebarNotesProps) {
  const tally = useMemo(() => {
    const counts: Record<string, number> = {};

    jobs.forEach((j) => {
      let loc = "Remote";
      if (j.locations && j.locations.length > 0 && j.locations[0]?.name) {
        loc = j.locations[0].name.split(",")[0].trim();
      } else if (j.locations_raw && j.locations_raw.length > 0) {
        loc = j.locations_raw[0].split(",")[0].trim();
      }
      loc = loc.replace("Bangalore", "Bengaluru").replace("Gurgaon", "Gurugram");
      if (loc) {
        counts[loc] = (counts[loc] || 0) + 1;
      }
    });

    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [jobs]);

  return (
    <aside className="notes" aria-label="Notes">
      <h2>Where this list is coming from</h2>
      <ul className="tally" id="tally">
        {tally.length > 0 ? (
          tally.map(([name, count]) => (
            <li key={name}>
              <span>{name}</span>
              <span>{count}</span>
            </li>
          ))
        ) : (
          <li style={{ color: "var(--mute)" }}>No locations in current view</li>
        )}
      </ul>
      <h2 style={{ marginTop: "18px" }}>Keys</h2>
      <dl className="keys">
        <dt>j / k</dt>
        <dd>next or previous job</dd>
        <dt>Enter</dt>
        <dd>open it</dd>
        <dt>/</dt>
        <dd>search</dd>
      </dl>
    </aside>
  );
}
