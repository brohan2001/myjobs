"use client";

import Link from "next/link";
import { formatAtsName } from "@/lib/ats";
import { formatExperience, formatSalary, jobWhen } from "@/lib/format";
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
  // A company's post date, our crawler's first sighting, or unknown (a board's first crawl).
  const when = jobWhen(job);
  // Fresh (< 60 minutes) only when the company says so: a crawl time can't vouch for a job's age.
  const isFresh = when.kind === "posted" && Date.now() - new Date(job.listed_at!).getTime() < 3_600_000;

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
  const expText = formatExperience(job.experience);
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
      <p className={`when when-${when.kind}`} title={when.title}>
        {when.text}
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
          {expText && (
            <span className={job.experience?.estimated ? "exp exp-estimated" : "exp"} title={job.experience?.estimated ? "estimated from the title" : "stated in the posting"}>
              {expText}
            </span>
          )}
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
