"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  COMPANY_TYPES,
  CURRENCIES,
  EXPERIENCE,
  PassThroughFilter,
  PLACES,
  WINDOWS,
  WORK_MODES,
} from "@/lib/constants";
import { Stats } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";

interface FeedHeaderProps {
  stats: Stats | null;
  filters: Record<PassThroughFilter, string>;
  placeValue: string;
  since: string;
  currency: string;
  searchQuery: string;
  onFilterChange: (key: string, value: string) => void;
  onSearchChange: (query: string) => void;
}

export function FeedHeader({
  stats,
  filters,
  placeValue,
  since,
  currency,
  searchQuery,
  onFilterChange,
  onSearchChange,
}: FeedHeaderProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery);

  useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  // Search runs on Enter, not per keystroke. Clearing the box (Esc or the ✕) applies at once.
  const handleSearchInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setLocalSearch(val);
    if (val === "" && searchQuery !== "") onSearchChange("");
  };
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (localSearch.trim() !== searchQuery) onSearchChange(localSearch);
  };

  // Find labels for the active sentence values
  const workMode = filters.work_mode;
  const currentMode = WORK_MODES.find((m) => m.value === workMode) ?? WORK_MODES[0];
  const currentPlace = PLACES.find((p) => p.value === placeValue) ?? PLACES[0];
  const currentSince = WINDOWS.find((w) => w.value === since) ?? WINDOWS[1];
  const currentCurrency = CURRENCIES.find((c) => c.value === currency) ?? CURRENCIES[0];

  // Freshness calculation
  let freshnessText = "Updated 4 min ago · 394,860 open jobs · 2,569 companies";
  if (stats) {
    let minAgo = 4;
    if (stats.last_updated) {
      const diffMs = Date.now() - new Date(stats.last_updated).getTime();
      minAgo = Math.max(1, Math.round(diffMs / 60000));
    } else if (stats.updated_minutes_ago) {
      minAgo = stats.updated_minutes_ago;
    }
    const jobsCount = (stats.active_jobs ?? 394860).toLocaleString("en-US");
    const companiesCount = (stats.companies_hiring ?? 2569).toLocaleString("en-US");
    freshnessText = `Updated ${minAgo} min ago · ${jobsCount} open jobs · ${companiesCount} companies`;
  }

  return (
    <header>
      <div className="top">
        <p className="brand">
          <Link href="/">myjobs</Link>
        </p>
        <ThemeToggle />
      </div>
      <p className="fresh">{freshnessText}</p>
      <h1 className="sr">Newest jobs</h1>
      <form onSubmit={handleSubmit} role="search" aria-label="Filters">
        <p className="sentence">
          Showing{" "}
          <span className="ctl">
            <span data-label>{currentMode.label}</span>
            <select
              value={workMode}
              onChange={(e) => onFilterChange("work_mode", e.target.value)}
              aria-label="Work mode"
            >
              {WORK_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </span>{" "}
          jobs{" "}
          <span className="ctl">
            <span data-label>{currentPlace.label}</span>
            <select
              value={placeValue}
              onChange={(e) => onFilterChange("place", e.target.value)}
              aria-label="Place"
            >
              {PLACES.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </span>{" "}
          at{" "}
          <SentenceSelect
            options={COMPANY_TYPES}
            value={filters.company_type}
            label="Company type"
            onChange={(v) => onFilterChange("company_type", v)}
          />{" "}
          for{" "}
          <SentenceSelect
            options={EXPERIENCE}
            value={filters.max_years}
            label="Experience"
            onChange={(v) => onFilterChange("max_years", v)}
          />
          , from the{" "}
          <span className="ctl dot">
            <span data-label>{currentSince.label}</span>
            <select
              value={since}
              onChange={(e) => onFilterChange("since", e.target.value)}
              aria-label="Posted within"
            >
              {WINDOWS.map((w) => (
                <option key={w.value} value={w.value}>
                  {w.label}
                </option>
              ))}
            </select>
          </span>{" "}
          Pay shown{" "}
          <span className="ctl dot">
            <span data-label>{currentCurrency.label}</span>
            <select
              value={currency}
              onChange={(e) => onFilterChange("cur", e.target.value)}
              aria-label="Currency"
            >
              {CURRENCIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </span>
        </p>
        <label className="find" htmlFor="q">
          <span className="t">Looking for something?</span>
          <input
            id="q"
            type="search"
            value={localSearch}
            onChange={handleSearchInput}
            placeholder="Press / to search, Enter to run"
            autoComplete="off"
          />
        </label>
      </form>
    </header>
  );
}

interface SentenceSelectProps {
  options: readonly { value: string; label: string }[];
  value: string;
  label: string;
  onChange: (value: string) => void;
}

function SentenceSelect({ options, value, label, onChange }: SentenceSelectProps) {
  const current = options.find((o) => o.value === value) ?? options[0];
  return (
    <span className="ctl">
      <span data-label>{current.label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </span>
  );
}
