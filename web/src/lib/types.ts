export interface LocationItem {
  id: number | null;
  name: string | null;
  country: string | null;
  type: string | null;
}

export interface Company {
  slug: string;
  name: string;
  website: string | null;
  logo: string | null;
}

export interface Salary {
  min: number;
  max: number | null;
  currency: string;
  period: string;
}

export interface Job {
  id: string;
  title: string;
  url: string;
  company: Company;
  locations: LocationItem[];
  locations_raw: string[];
  work_modes: string[];
  employment_type: string | null;
  salary: Salary | null;
  ats: string;
  first_seen_at: string;
  last_seen_at: string;
  is_active?: boolean;
  description_html?: string | null;
}

export interface JobsResponse {
  jobs: Job[];
  next_cursor: string | null;
}

export interface Stats {
  active_jobs: number;
  new_last_24h: number;
  companies_hiring: number;
  last_updated: string | null;
  updated_minutes_ago?: number;
}

export interface LocationSearchResult {
  id: number;
  name: string;
  type: string;
  code: string | null;
}
