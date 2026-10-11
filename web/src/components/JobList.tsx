"use client";

import { useEffect, useState } from "react";
import { timeBucket } from "@/lib/format";
import { Job } from "@/lib/types";
import { JobRow } from "./JobRow";

interface JobListProps {
  jobs: Job[];
  currency: string;
  isLoading: boolean;
  isError: boolean;
  companiesHiring?: number;
  placeLabel: string;
  winPhrase: string;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onRetry: () => void;
  onWidenWindow?: () => void;
  onLookWorldwide?: () => void;
  onClearFilters?: () => void;
  focusedIndex: number;
  setFocusedIndex: (i: number) => void;
  onOpenJob: (job: Job) => void;
}

export function JobList({
  jobs,
  currency,
  isLoading,
  isError,
  companiesHiring = 2569,
  placeLabel,
  winPhrase,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onRetry,
  onWidenWindow,
  onLookWorldwide,
  onClearFilters,
  focusedIndex,
  setFocusedIndex,
  onOpenJob,
}: JobListProps) {
  const [lastVisitDate, setLastVisitDate] = useState<Date | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("lastVisit");
      if (stored) {
        setLastVisitDate(new Date(stored));
      } else {
        // Record first visit
        localStorage.setItem("lastVisit", new Date().toISOString());
      }
    } catch {}
  }, []);

  // Format last visit date for divider
  const formattedLastVisit = lastVisitDate
    ? lastVisitDate.toLocaleDateString("en-US", {
        weekday: "long",
        day: "numeric",
        month: "short",
      })
    : "your last visit";

  // Calculate new jobs since last visit
  const newJobsCount = lastVisitDate
    ? jobs.filter((j) => new Date(j.first_seen_at) > lastVisitDate).length
    : 0;

  if (isLoading) {
    return (
      <ol id="list" aria-label="Jobs, newest first" aria-busy="true">
        <li className="state-load" role="status">
          <span className="sr">Loading the newest jobs</span>
          <p className="load-line">
            Checking {companiesHiring.toLocaleString("en-US")} career sites for new postings…
          </p>
        </li>
        {Array.from({ length: 9 }).map((_, i) => (
          <li key={i} className="sk" aria-hidden="true">
            <i />
            <i />
            <i />
          </li>
        ))}
      </ol>
    );
  }

  if (isError) {
    return (
      <ol id="list" aria-label="Jobs, newest first">
        <li className="state state-error" role="alert">
          <p className="state-h">We can’t reach the feed right now.</p>
          <p className="state-p">
            That’s on our side, not your connection. Give it a moment, then try again.
          </p>
          <div className="state-b">
            <button className="btn" type="button" onClick={onRetry}>
              Try again
            </button>
          </div>
        </li>
      </ol>
    );
  }

  if (jobs.length === 0) {
    return (
      <ol id="list" aria-label="Jobs, newest first">
        <li className="state state-empty" role="status">
          <p className="state-h">
            Nothing {placeLabel} in the {winPhrase}.
          </p>
          <p className="state-p">
            Postings land in bursts. A wider window usually helps.
          </p>
          <div className="state-b">
            {onWidenWindow && (
              <button className="btn" type="button" onClick={onWidenWindow}>
                Widen time window?
              </button>
            )}
            {onLookWorldwide && (
              <button className="btn" type="button" onClick={onLookWorldwide}>
                Look worldwide
              </button>
            )}
            {onClearFilters && (
              <button className="btn btn-quiet" type="button" onClick={onClearFilters}>
                Clear search and mode
              </button>
            )}
          </div>
        </li>
      </ol>
    );
  }

  // Group jobs by timeBucket and insert divider
  let lastBucket: string | null = null;
  const elements: React.ReactNode[] = [];
  let dividerInserted = false;

  jobs.forEach((job, index) => {
    const bucket = timeBucket(job.first_seen_at);

    // Group header
    if (bucket !== lastBucket) {
      elements.push(
        <li key={`bucket-${bucket}`} className="group-header" role="presentation">
          <span>{bucket}</span>
        </li>
      );
      lastBucket = bucket;
    }

    // Divider: new since your last visit
    if (
      !dividerInserted &&
      newJobsCount > 0 &&
      newJobsCount < jobs.length &&
      index === newJobsCount
    ) {
      elements.push(
        <li key="new-visit-divider" className="div" role="separator">
          {newJobsCount} new since your last visit on {formattedLastVisit}. Everything below you have probably seen.
        </li>
      );
      dividerInserted = true;
    }

    elements.push(
      <JobRow
        key={job.id}
        job={job}
        index={index}
        currency={currency}
        isFocused={focusedIndex === index}
        onFocus={() => setFocusedIndex(index)}
        onOpen={() => onOpenJob(job)}
      />
    );
  });

  return (
    <>
      <ol id="list" aria-label="Jobs, newest first">
        {elements}
      </ol>
      {hasMore && (
        <div className="load-more-section">
          <button
            className="btn btn-quiet"
            type="button"
            onClick={onLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? "Loading more…" : "Load more jobs"}
          </button>
        </div>
      )}
    </>
  );
}
