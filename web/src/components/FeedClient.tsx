"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchJobs } from "@/lib/api";
import { collapseRuns } from "@/lib/collapse";
import { PLACES, WINDOWS } from "@/lib/constants";
import { Job, Stats } from "@/lib/types";
import { FeedHeader } from "./FeedHeader";
import { JobList, VisibleFeedItem } from "./JobList";
import { SidebarNotes } from "./SidebarNotes";

interface FeedClientProps {
  initialJobs: Job[];
  initialNextCursor: string | null;
  initialStats: Stats | null;
  initialError: boolean;
  footer?: React.ReactNode;
}

export function FeedClient({
  initialJobs,
  initialNextCursor,
  initialStats,
  initialError,
  footer,
}: FeedClientProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // URL state
  const countryParam = searchParams.get("country");
  const locationParam = searchParams.get("location");
  const companyParam = searchParams.get("company") ?? "";
  const workModeParam = searchParams.get("work_mode") ?? "";
  const sinceParam = searchParams.get("since") ?? "24h";
  const qParam = searchParams.get("q") ?? "";

  // Derive place value
  let initialPlace = "in:"; // Default India
  if (locationParam) {
    initialPlace = `in:${locationParam}`;
  } else if (countryParam) {
    if (countryParam.toUpperCase() === "IN") initialPlace = "in:";
    else if (countryParam.toUpperCase() === "US") initialPlace = "us:";
    else if (countryParam.toUpperCase() === "EU") initialPlace = "eu:";
    else if (countryParam.toLowerCase() === "all") initialPlace = "all:";
  }

  // Local state
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [nextCursor, setNextCursor] = useState<string | null>(initialNextCursor);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isError, setIsError] = useState(initialError);
  const [currency, setCurrency] = useState("native");
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [expandedRunKeys, setExpandedRunKeys] = useState<Set<string>>(() => new Set());

  // Sync initial jobs when initial props change
  useEffect(() => {
    setJobs(initialJobs);
    setNextCursor(initialNextCursor);
    setIsError(initialError);
    setFocusedIndex(-1);
    setExpandedRunKeys(new Set());
  }, [initialJobs, initialNextCursor, initialError]);

  // Load currency preference from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem("payCurrency");
      if (stored) {
        setCurrency(stored);
      }
    } catch {}
  }, []);

  // Update URL helper
  const updateQueryParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([key, value]) => {
        if (value === null || value === "") {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      });
      const query = params.toString();
      router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  // Filter change handler
  const handleFilterChange = (key: string, value: string) => {
    if (key === "cur") {
      setCurrency(value);
      try {
        localStorage.setItem("payCurrency", value);
      } catch {}
      return;
    }

    if (key === "place") {
      const selected = PLACES.find((p) => p.value === value);
      if (selected) {
        if (selected.location) {
          updateQueryParams({ location: String(selected.location), country: null });
        } else if (selected.country) {
          updateQueryParams({ country: selected.country, location: null });
        } else {
          // Worldwide
          updateQueryParams({ country: "all", location: null });
        }
      }
      return;
    }

    if (key === "work_mode") {
      updateQueryParams({ work_mode: value || null });
      return;
    }

    if (key === "since") {
      updateQueryParams({ since: value });
      return;
    }
  };

  // Search debounce handler
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const handleSearchChange = (val: string) => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      updateQueryParams({ q: val.trim() || null });
    }, 250);
  };

  // Load more jobs
  const handleLoadMore = async () => {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const selectedPlace = PLACES.find((p) => p.value === initialPlace);
      const res = await fetchJobs({
        q: qParam,
        country: selectedPlace?.country,
        location: selectedPlace?.location,
        company: companyParam || undefined,
        work_mode: workModeParam,
        since: sinceParam,
        cursor: nextCursor,
      });
      setJobs((prev) => [...prev, ...res.jobs]);
      setNextCursor(res.next_cursor);
    } catch {
      showToast("Could not load more jobs. Try again.");
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Retry fetch
  const handleRetry = async () => {
    setIsLoading(true);
    setIsError(false);
    try {
      const selectedPlace = PLACES.find((p) => p.value === initialPlace);
      const res = await fetchJobs({
        q: qParam,
        country: selectedPlace?.country,
        location: selectedPlace?.location,
        company: companyParam || undefined,
        work_mode: workModeParam,
        since: sinceParam,
      });
      setJobs(res.jobs);
      setNextCursor(res.next_cursor);
    } catch {
      setIsError(true);
    } finally {
      setIsLoading(false);
    }
  };

  // Toast notification
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const showToast = (msg: string) => {
    setToastMessage(msg);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 2600);
  };

  // Open job
  const handleOpenJob = useCallback((job: Job) => {
    window.open(job.url, "_blank", "noopener,noreferrer");
  }, []);

  // Collapse runs and compute visible items
  const collapsedItems = useMemo(() => collapseRuns(jobs), [jobs]);

  const visibleItems = useMemo(() => {
    const items: VisibleFeedItem[] = [];
    for (const item of collapsedItems) {
      if (item.kind === "job") {
        items.push(item);
      } else {
        const runKey = `${item.company.slug}:${item.hidden[0]?.id}`;
        if (expandedRunKeys.has(runKey)) {
          for (const job of item.hidden) {
            items.push({ kind: "job", job });
          }
        } else {
          items.push({ ...item, runKey });
        }
      }
    }
    return items;
  }, [collapsedItems, expandedRunKeys]);

  const handleExpandRun = useCallback((runKey: string) => {
    setExpandedRunKeys((prev) => {
      const next = new Set(prev);
      next.add(runKey);
      return next;
    });
  }, []);

  const buildCompanyHref = useCallback(
    (slug: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("company", slug);
      params.delete("cursor");
      const qs = params.toString();
      return qs ? `/?${qs}` : `/?company=${encodeURIComponent(slug)}`;
    },
    [searchParams]
  );

  // Keep focus in view when visible items expand
  useEffect(() => {
    if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
      const active = document.activeElement;
      if (active && active !== document.body && active.tagName !== "INPUT") {
        const el = document.querySelector(`[data-i="${focusedIndex}"]`) as HTMLElement | null;
        el?.focus();
      }
    }
  }, [visibleItems, focusedIndex]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();

      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (tag === "input") {
        if (e.key === "Escape") {
          target?.blur();
        }
        return;
      }

      if (tag === "select" || tag === "textarea") return;

      if (e.key === "/") {
        e.preventDefault();
        const input = document.getElementById("q") as HTMLInputElement | null;
        input?.focus();
      } else if (e.key === "j") {
        e.preventDefault();
        setFocusedIndex((prev) => {
          const next = Math.min(visibleItems.length - 1, prev + 1);
          const el = document.querySelector(`[data-i="${next}"]`) as HTMLElement | null;
          el?.focus();
          el?.scrollIntoView({ block: "nearest" });
          return next;
        });
      } else if (e.key === "k") {
        e.preventDefault();
        setFocusedIndex((prev) => {
          const next = Math.max(0, prev - 1);
          const el = document.querySelector(`[data-i="${next}"]`) as HTMLElement | null;
          el?.focus();
          el?.scrollIntoView({ block: "nearest" });
          return next;
        });
      } else if (e.key === "Enter") {
        if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
          const item = visibleItems[focusedIndex];
          if (item.kind === "job") {
            e.preventDefault();
            handleOpenJob(item.job);
          } else if (item.kind === "more") {
            e.preventDefault();
            handleExpandRun(item.runKey);
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [visibleItems, focusedIndex, handleExpandRun, handleOpenJob]);

  // Labels for place and window
  const activePlace = PLACES.find((p) => p.value === initialPlace) ?? PLACES[0];
  const activeWin = WINDOWS.find((w) => w.value === sinceParam) ?? WINDOWS[1];

  // Count text
  const countText = `${jobs.length} ${
    jobs.length === 1 ? "job" : "jobs"
  } ${activePlace.label}, ${activeWin.label}`;

  // Widen window helper
  const handleWidenWindow = () => {
    const idx = WINDOWS.findIndex((w) => w.value === sinceParam);
    const nextWin = WINDOWS[Math.min(idx + 1, WINDOWS.length - 1)];
    updateQueryParams({ since: nextWin.value });
  };

  const handleLookWorldwide = () => {
    updateQueryParams({ country: "all", location: null });
  };

  const handleClearFilters = () => {
    updateQueryParams({ q: null, work_mode: null, company: null });
  };

  return (
    <div className="wrap">
      <FeedHeader
        stats={initialStats}
        workMode={workModeParam}
        placeValue={initialPlace}
        since={sinceParam}
        currency={currency}
        searchQuery={qParam}
        onFilterChange={handleFilterChange}
        onSearchChange={handleSearchChange}
      />
      <div className="cols">
        <main>
          <p className="count" data-out="count" aria-live="polite">
            {isLoading ? "Loading…" : isError ? "Feed unavailable" : countText}
          </p>
          <JobList
            jobs={jobs}
            visibleItems={visibleItems}
            currency={currency}
            placeFilter={initialPlace}
            isLoading={isLoading}
            isError={isError}
            companiesHiring={initialStats?.companies_hiring}
            placeLabel={activePlace.label}
            winPhrase={activeWin.label}
            hasMore={Boolean(nextCursor)}
            isLoadingMore={isLoadingMore}
            onLoadMore={handleLoadMore}
            onRetry={handleRetry}
            onWidenWindow={handleWidenWindow}
            onLookWorldwide={handleLookWorldwide}
            onClearFilters={handleClearFilters}
            focusedIndex={focusedIndex}
            setFocusedIndex={setFocusedIndex}
            onOpenJob={handleOpenJob}
            onExpandRun={handleExpandRun}
            buildCompanyHref={buildCompanyHref}
          />
        </main>
        <SidebarNotes jobs={jobs} />
      </div>
      {footer}
      <div
        id="toast"
        className={`toast ${toastMessage ? "on" : ""}`}
        role="status"
        aria-live="polite"
      >
        {toastMessage}
      </div>
    </div>
  );
}
