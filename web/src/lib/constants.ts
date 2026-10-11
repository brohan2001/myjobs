export interface PlaceOption {
  value: string;
  label: string;
  country?: string;
  location?: number;
}

export const CITIES = [
  { id: 1277333, name: "Bengaluru", slug: "blr" },
  { id: 1275339, name: "Mumbai", slug: "bom" },
  { id: 1273294, name: "Delhi NCR", slug: "ncr" },
  { id: 1269843, name: "Hyderabad", slug: "hyd" },
  { id: 1259229, name: "Pune", slug: "pnq" },
  { id: 1264527, name: "Chennai", slug: "maa" },
] as const;

export const PLACES: PlaceOption[] = [
  { value: "in:", label: "in India", country: "IN" },
  { value: "in:1277333", label: "in Bengaluru", location: 1277333 },
  { value: "in:1275339", label: "in Mumbai", location: 1275339 },
  { value: "in:1273294", label: "in Delhi NCR", location: 1273294 },
  { value: "in:1269843", label: "in Hyderabad", location: 1269843 },
  { value: "in:1259229", label: "in Pune", location: 1259229 },
  { value: "in:1264527", label: "in Chennai", location: 1264527 },
  { value: "all:", label: "worldwide" },
  { value: "us:", label: "in the US", country: "US" },
  { value: "eu:", label: "in the EU or UK", country: "EU" },
];

export const WORK_MODES = [
  { value: "", label: "all" },
  { value: "remote", label: "remote" },
  { value: "hybrid", label: "hybrid" },
  { value: "onsite", label: "on-site" },
] as const;

export const WINDOWS = [
  { value: "1h", label: "last hour" },
  { value: "24h", label: "last 24 hours" },
  { value: "3d", label: "last 3 days" },
  { value: "7d", label: "last 7 days" },
] as const;

export const CURRENCIES = [
  { value: "native", label: "as posted" },
  { value: "INR", label: "in rupees" },
  { value: "USD", label: "in dollars" },
] as const;

// Sentence filters passed straight through to /api/v1/jobs (URL param = API param).
export const COMPANY_TYPES = [
  { value: "", label: "any company" },
  { value: "startup", label: "startups" },
  { value: "product", label: "product companies" },
  { value: "mnc", label: "MNCs" },
  { value: "gcc", label: "global capability centres" },
  { value: "services", label: "services firms" },
] as const;

export const EXPERIENCE = [
  { value: "", label: "any experience" },
  { value: "0", label: "freshers" },
  { value: "2", label: "up to 2 years" },
  { value: "5", label: "up to 5 years" },
  { value: "10", label: "up to 10 years" },
] as const;

export const NOTICE = [
  { value: "", label: "any notice period" },
  { value: "30", label: "a 30-day notice" },
  { value: "60", label: "a 60-day notice" },
  { value: "90", label: "a 90-day notice" },
] as const;

export const PASS_THROUGH_FILTERS = ["work_mode", "company_type", "max_years", "notice_days"] as const;
export type PassThroughFilter = (typeof PASS_THROUGH_FILTERS)[number];
