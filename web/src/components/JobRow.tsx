"use client";

import Link from "next/link";
import { ATS_NAMES, WORK_MODE_NAMES } from "@/lib/constants";
import { formatSalary, relativeTime } from "@/lib/format";
import { orderLocations } from "@/lib/locations";
import { RATES } from "@/lib/rates";
import { Job } from "@/lib/types";

interface JobRowProps {
  job: Job;
  index: number;
  currency: string;
  placeFilter?: string;
  isFocused?: boolean;
  onFocus?: () => void;
  onOpen?: () => void;
}

export function JobRow({
  job,
  index,
  currency,
  placeFilter,
  isFocused = false,
  onFocus,
  onOpen,
}: JobRowProps) {
  // Freshness check (< 60 minutes)
  const firstSeenMs = new Date(job.first_seen_at).getTime();
  const ageMin = Math.max(0, Math.round((Date.now() - firstSeenMs) / 60000));
  const isFresh = ageMin < 60;

  // Relative time string
  const timeString = relativeTime(job.first_seen_at);

  // Formatted location
  let locationText = "Remote";
  const orderedLocations = orderLocations(job.locations, placeFilter);
  if (orderedLocations && orderedLocations.length > 0) {
    const valid = orderedLocations.filter((l) => l.name);
    if (valid.length > 0) {
      const first = valid[0].name ?? "";
      locationText = valid.length > 1 ? `${first} +${valid.length - 1}` : first;
    } else if (job.locations_raw && job.locations_raw.length > 0) {
      locationText = job.locations_raw[0];
    }
  } else if (job.locations_raw && job.locations_raw.length > 0) {
    locationText = job.locations_raw[0];
  }

  // Work modes formatted
  const modesText = (job.work_modes || [])
    .map((m) => WORK_MODE_NAMES[m.toLowerCase()] ?? m)
    .join(" / ");

  // Salary formatted
  const salaryText = formatSalary(job.salary, currency, RATES);

  // ATS formatted
  const atsName = ATS_NAMES[job.ats?.toLowerCase()] ?? job.ats;

  return (
    <li
      className={`row ${isFresh ? "is-fresh" : ""} ${isFocused ? "focused" : ""}`}
      data-i={index}
      tabIndex={isFocused ? 0 : -1}
      onFocus={onFocus}
      onClick={(e) => {
        // If clicking inside anchor, let default link action occur
        if ((e.target as HTMLElement).closest("a")) {
          return;
        }
        if (onOpen) {
          onOpen();
        }
      }}
    >
      <p className="when">{timeString}</p>
      <div className="body">
        <a
          className="title"
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {job.title}
        </a>
        <p className="where">
          <b>{job.company.name}</b> in {locationText}
        </p>
        <p className="tags">
          {modesText && <span className="mode">{modesText}</span>}
          {salaryText && <span className="pay">{salaryText}</span>}
          {atsName && <span>via {atsName}</span>}
          <Link
            href={`/jobs/${job.id}`}
            style={{
              fontSize: "13px",
              color: "var(--mute)",
              marginLeft: "auto",
              textDecoration: "underline",
            }}
          >
            Details
          </Link>
        </p>
      </div>
    </li>
  );
}
