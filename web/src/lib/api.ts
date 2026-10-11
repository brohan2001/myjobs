import { Job, JobsResponse, LocationSearchResult, Stats } from "./types";

const DEFAULT_API_ORIGIN = "http://127.0.0.1:8090";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    // Server-side
    return process.env.API_ORIGIN ?? DEFAULT_API_ORIGIN;
  }
  // Client-side: use relative path so Next.js rewrite proxies to API
  return "";
}

export interface FetchJobsParams {
  q?: string;
  country?: string;
  location?: number | string;
  company?: string;
  work_mode?: string;
  since?: string;
  cursor?: string;
  limit?: number;
}

export async function fetchJobs(params: FetchJobsParams = {}): Promise<JobsResponse> {
  const baseUrl = getApiBaseUrl();
  const searchParams = new URLSearchParams();

  if (params.q?.trim()) {
    searchParams.set("q", params.q.trim());
  }
  if (params.country?.trim()) {
    searchParams.set("country", params.country.trim());
  }
  if (params.location !== undefined && params.location !== "") {
    searchParams.set("location", String(params.location));
  }
  if (params.company?.trim()) {
    searchParams.set("company", params.company.trim());
  }
  if (params.work_mode?.trim()) {
    searchParams.set("work_mode", params.work_mode.trim());
  }
  if (params.since?.trim()) {
    searchParams.set("since", params.since.trim());
  }
  if (params.cursor?.trim()) {
    searchParams.set("cursor", params.cursor.trim());
  }
  if (params.limit) {
    searchParams.set("limit", String(params.limit));
  }

  const query = searchParams.toString();
  const url = `${baseUrl}/api/v1/jobs${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch jobs: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

export async function fetchJob(id: string): Promise<Job | null> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/v1/jobs/${encodeURIComponent(id)}`;

  const res = await fetch(url, {
    cache: "no-store",
  });

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    throw new Error(`Failed to fetch job ${id}: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

export async function fetchStats(): Promise<Stats | null> {
  try {
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/api/v1/stats`;

    const res = await fetch(url, {
      cache: "no-store",
    });

    if (!res.ok) {
      return null;
    }

    return res.json();
  } catch {
    return null;
  }
}

export async function fetchLocations(query: string): Promise<LocationSearchResult[]> {
  if (!query.trim()) {
    return [];
  }
  try {
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/api/v1/locations?q=${encodeURIComponent(query.trim())}`;

    const res = await fetch(url, {
      cache: "no-store",
    });

    if (!res.ok) {
      return [];
    }

    const data = await res.json();
    return data.locations ?? [];
  } catch {
    return [];
  }
}
