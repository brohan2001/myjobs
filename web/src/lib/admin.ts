// Server-only helpers for /admin: they send ADMIN_TOKEN, so never import this from a "use client" component.
import { getApiBaseUrl } from "./api";

export interface Overview {
  stats: {
    active_jobs: number;
    new_last_24h: number;
    companies_hiring: number;
    boards_enabled: number;
    boards_fresh_24h: number;
    boards_failing: number;
    last_updated: string | null;
  };
  health: {
    feed_age_minutes: number | null;
    active_boards: number;
    overdue_boards: number;
    gone_last_day: number;
    alerts: { check: string; message: string }[];
  };
  queues: Record<"simple" | "browser", { ready_now: number; inflight: number; deadletter: number }> | null;
  backup: { file: string; bytes: number; at: string } | null;
}

export interface Board {
  id: string;
  company: string;
  company_name: string;
  board_slug: string | null;
  board_url: string;
  crawler_type: string | null;
  board_status: string;
  is_enabled: boolean;
  last_checked_at: string | null;
  last_success_at: string | null;
  next_check_at: string;
  consecutive_failures: number;
  last_error: string | null;
  active_jobs: number;
}

export interface ErrorGroup {
  error: string;
  boards: number;
  ats: string[];
}

export interface Service {
  unit: string;
  state: string | null;
  sub_state: string | null;
  restarts: number | null;
  uptime_s: number | null;
  memory_bytes: number | null;
  memory_peak_bytes: number | null;
  memory_max_bytes: number | null;
  cpu_percent: number | null;
  cpu_quota_percent: number | null;
}

export interface SystemStats {
  host: {
    cpu_count: number;
    cpu_percent_per_core: number[];
    load_avg: number[];
    cpu_temp_c: number | null;
    memory: { total: number; used: number; percent: number };
    swap: { total: number; used: number; percent: number };
    disk: { total: number; used: number; percent: number };
    gpu: { freq_mhz: number; max_mhz: number; percent: number | null } | null;
  };
  services: Service[];
  containers: {
    name: string;
    cpu_percent: number | null;
    cpu_quota_percent: number | null;
    memory_bytes: number | null;
    memory_max_bytes: number | null;
  }[];
}

export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}/api/admin${path}`, {
    ...init,
    cache: "no-store",
    headers: { Authorization: `Bearer ${process.env.ADMIN_TOKEN ?? ""}` },
  });
  if (!res.ok) {
    throw new Error(`admin API ${path}: ${res.status}`);
  }
  return res.json();
}

/** "5 min ago" for past times, "in 5 min" for future ones (next checks). */
export function since(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "never";
  const sec = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  const abs = Math.abs(sec);
  const amount =
    abs < 60 ? `${abs} s` : abs < 7200 ? `${Math.round(abs / 60)} min` : abs < 172800 ? `${Math.round(abs / 3600)} h` : `${Math.round(abs / 86400)} days`;
  return sec >= 0 ? `${amount} ago` : `in ${amount}`;
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i >= 3 ? 1 : 0)} ${units[i]}`;
}

export function duration(s: number | null): string {
  if (s == null) return "–";
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} days`;
}
