import { CITIES } from "./constants";
import { LocationItem } from "./types";

export const EU_COUNTRIES = new Set([
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
  "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
  "PL", "PT", "RO", "SK", "SI", "ES", "SE",
]);

export interface LocationFilterObject {
  country?: string | null;
  city?: string | null;
  name?: string | null;
  location?: number | string | null;
}

export type LocationFilter = string | LocationFilterObject | null | undefined;

interface ParsedFilter {
  type: "country" | "eu" | "city" | "none";
  value?: string;
  locationId?: number;
}

const CITY_SLUGS: Record<string, string> = {
  blr: "Bengaluru",
  bom: "Mumbai",
  ncr: "Delhi NCR",
  hyd: "Hyderabad",
  pnq: "Pune",
  maa: "Chennai",
};

function parseFilter(filter?: LocationFilter): ParsedFilter {
  if (!filter) return { type: "none" };

  if (typeof filter === "object") {
    if (filter.country) {
      const c = filter.country.toUpperCase();
      if (c === "EU") return { type: "eu" };
      if (c === "ALL") return { type: "none" };
      return { type: "country", value: c };
    }
    if (filter.city || filter.name) {
      return { type: "city", value: (filter.city || filter.name) ?? "" };
    }
    if (filter.location != null) {
      const numId = Number(filter.location);
      const city = CITIES.find((c) => c.id === numId);
      if (city) return { type: "city", value: city.name, locationId: numId };
      return { type: "city", locationId: numId };
    }
    return { type: "none" };
  }

  const s = filter.trim();
  if (!s || s === "all:" || s.toLowerCase() === "all" || s.toLowerCase() === "worldwide") {
    return { type: "none" };
  }

  // Handle prefix styles like in:, us:, eu:, in:1277333, in:blr
  if (s.startsWith("in:")) {
    const sub = s.slice(3).trim();
    if (!sub) return { type: "country", value: "IN" };
    if (CITY_SLUGS[sub.toLowerCase()]) {
      return { type: "city", value: CITY_SLUGS[sub.toLowerCase()] };
    }
    const numId = Number(sub);
    if (!Number.isNaN(numId)) {
      const city = CITIES.find((c) => c.id === numId);
      if (city) return { type: "city", value: city.name, locationId: numId };
    }
    return { type: "city", value: sub };
  }

  if (s === "us:" || s.toUpperCase() === "US" || s.toLowerCase() === "in the us" || s.toLowerCase() === "united states") {
    return { type: "country", value: "US" };
  }

  if (s === "eu:" || s.toUpperCase() === "EU" || s.toLowerCase() === "in the eu or uk" || s.toLowerCase() === "europe") {
    return { type: "eu" };
  }

  if (s.toUpperCase() === "IN" || s.toLowerCase() === "in india" || s.toLowerCase() === "india") {
    return { type: "country", value: "IN" };
  }

  // If slug matches known city
  if (CITY_SLUGS[s.toLowerCase()]) {
    return { type: "city", value: CITY_SLUGS[s.toLowerCase()] };
  }

  // Otherwise assume city name
  return { type: "city", value: s.replace(/^in\s+/i, "") };
}

function matchesCity(loc: LocationItem, cityName: string): boolean {
  if (!loc.name) return false;
  const raw = loc.name.toLowerCase();
  const target = cityName.toLowerCase();

  // Alias-aware checks for Indian metropolitan regions
  if (target.includes("bengaluru") || target.includes("bangalore")) {
    return raw.includes("bengaluru") || raw.includes("bangalore");
  }
  if (target.includes("delhi") || target.includes("ncr")) {
    return raw.includes("delhi") || raw.includes("noida") || raw.includes("gurugram") || raw.includes("gurgaon") || raw.includes("ncr");
  }
  if (target.includes("mumbai") || target.includes("bombay")) {
    return raw.includes("mumbai") || raw.includes("bombay");
  }

  return raw.includes(target);
}

function matchesLocation(loc: LocationItem, parsed: ParsedFilter): boolean {
  if (parsed.type === "none") return false;

  if (parsed.type === "country" && parsed.value) {
    return (loc.country?.toUpperCase() ?? "") === parsed.value;
  }

  if (parsed.type === "eu") {
    const code = loc.country?.toUpperCase() ?? "";
    return EU_COUNTRIES.has(code);
  }

  if (parsed.type === "city") {
    if (parsed.locationId != null && loc.id === parsed.locationId) {
      return true;
    }
    if (parsed.value) {
      return matchesCity(loc, parsed.value);
    }
  }

  return false;
}

export function orderLocations(
  locations: LocationItem[] | null | undefined,
  filter?: LocationFilter
): LocationItem[] {
  if (!locations || locations.length <= 1) {
    return locations ? [...locations] : [];
  }

  const parsed = parseFilter(filter);
  if (parsed.type === "none") {
    return [...locations];
  }

  const matches: LocationItem[] = [];
  const rest: LocationItem[] = [];

  for (const loc of locations) {
    if (matchesLocation(loc, parsed)) {
      matches.push(loc);
    } else {
      rest.push(loc);
    }
  }

  // If no location matched the filter, return original list preserved
  if (matches.length === 0) {
    return [...locations];
  }

  return [...matches, ...rest];
}
