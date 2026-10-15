"use client";

import Link from "next/link";
import { formatAtsName } from "@/lib/ats";
import { formatSalary, relativeTime } from "@/lib/format";
import { orderLocations } from "@/lib/locations";
import { RATES } from "@/lib/rates";
import { Job } from "@/lib/types";
import { formatWorkModes } from "@/lib/work_modes";

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
  // Freshness check (< 60 minutes). listed_at is the ATS's posting date when it gives one,
  // otherwise when we first saw the job.
  const listedMs = new Date(job.listed_at).getTime();
  const ageMin = Math.max(0, Math.round((Date.now() - listedMs) / 60000));
  const isFresh = ageMin < 60;

  const timeString = relativeTime(job.listed_at);

  // Formatted location
  let locationText = "Remote";
  const orderedLocations = orderLocations(job.locations, placeFilter);
  const validLocs = orderedLocations?.filter((l) => l.name);
  if (validLocs && validLocs.length > 0) {
    const first = validLocs[0].name ?? "";
    locationText = validLocs.length > 1 ? `${first} +${validLocs.length - 1}` : first;
  } else if (job.locations_raw?.[0]) {
    locationText = job.locations_raw[0];
  }

  // Work modes formatted (never "undefined", empty when array is empty)
  const modesText = formatWorkModes(job.work_modes);

  // Salary formatted
  const salaryText = formatSalary(job.salary, currency, RATES);

  // ATS formatted
  const atsName = formatAtsName(job.ats);

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
      <p className="when" title={job.posted_at ? "Posted by the company" : "First seen by our crawler"}>
        {timeString}
      </p>
      <div className="body">
        <a
          className="title"
          title={job.title}
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {job.title}
        </a>
        <p className="where" title={`${job.company.name} in ${locationText}`}>
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
