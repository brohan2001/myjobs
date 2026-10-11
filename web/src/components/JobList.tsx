"use client";

import { useEffect, useState } from "react";
import { timeBucket } from "@/lib/format";
import { Job } from "@/lib/types";
import { JobRow } from "./JobRow";
import { MoreRow } from "./MoreRow";

export type VisibleFeedItem =
  | { kind: "job"; job: Job }
  | {
      kind: "more";
      company: { slug: string; name: string };
      count: number;
      hidden: Job[];
      runKey: string;
    };

interface JobListProps {
  jobs: Job[];
  visibleItems: VisibleFeedItem[];
  currency: string;
  placeFilter?: string;
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
  onExpandRun: (runKey: string) => void;
  buildCompanyHref: (slug: string) => string;
}

export function JobList({
  jobs,
  visibleItems,
  currency,
  placeFilter,
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
  onExpandRun,
  buildCompanyHref,
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

  // Group visible items by timeBucket and insert divider
  let lastBucket: string | null = null;
  const elements: React.ReactNode[] = [];
  let dividerInserted = false;

  visibleItems.forEach((item, index) => {
    const jobForBucket = item.kind === "job" ? item.job : item.hidden[0];
    const bucket = timeBucket(jobForBucket.first_seen_at);

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
      lastVisitDate &&
      newJobsCount > 0 &&
      newJobsCount < jobs.length &&
      new Date(jobForBucket.first_seen_at) <= lastVisitDate
    ) {
      elements.push(
        <li key="new-visit-divider" className="div" role="separator">
          {newJobsCount} new since your last visit on {formattedLastVisit}. Everything below you have probably seen.
        </li>
      );
      dividerInserted = true;
    }

    if (item.kind === "job") {
      elements.push(
        <JobRow
          key={item.job.id}
          job={item.job}
          index={index}
          currency={currency}
          placeFilter={placeFilter}
          isFocused={focusedIndex === index}
          onFocus={() => setFocusedIndex(index)}
          onOpen={() => onOpenJob(item.job)}
        />
      );
    } else {
      elements.push(
        <MoreRow
          key={`more-${item.runKey}`}
          company={item.company}
          count={item.count}
          index={index}
          isFocused={focusedIndex === index}
          onFocus={() => setFocusedIndex(index)}
          onExpand={() => onExpandRun(item.runKey)}
          companyHref={buildCompanyHref(item.company.slug)}
        />
      );
    }
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
