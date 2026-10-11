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

const CITY_SLUGS: Record<string, string> = {
  blr: "bengaluru",
  bom: "mumbai",
  ncr: "delhi",
  hyd: "hyderabad",
  pnq: "pune",
  maa: "chennai",
};

const CITY_IDS: Record<number, string> = {
  1277333: "bengaluru",
  1275339: "mumbai",
  1273294: "delhi",
  1269843: "hyderabad",
  1259229: "pune",
  1264527: "chennai",
};

export function orderLocations(
  locations: LocationItem[] | null | undefined,
  filter?: LocationFilter
): LocationItem[] {
  if (!locations || locations.length <= 1 || !filter) {
    return locations ? [...locations] : [];
  }

  let country = "";
  let isEu = false;
  let city = "";
  let locId: number | undefined;

  if (typeof filter === "object") {
    if (filter.country) {
      const c = filter.country.toUpperCase();
      if (c === "EU") isEu = true;
      else if (c !== "ALL") country = c;
    }
    city = (filter.city || filter.name || "").toLowerCase();
    if (filter.location != null) locId = Number(filter.location);
  } else {
    const s = filter.trim();
    if (!s || s === "all:" || s.toLowerCase() === "all" || s.toLowerCase() === "worldwide") {
      return [...locations];
    }
    if (s.startsWith("in:")) {
      const sub = s.slice(3).toLowerCase();
      if (!sub) country = "IN";
      else if (CITY_SLUGS[sub]) city = CITY_SLUGS[sub];
      else if (!Number.isNaN(Number(sub))) locId = Number(sub);
      else city = sub;
    } else if (s === "us:" || s.toUpperCase() === "US" || s.toLowerCase() === "in the us" || s.toLowerCase() === "united states") {
      country = "US";
    } else if (s === "eu:" || s.toUpperCase() === "EU" || s.toLowerCase() === "in the eu or uk" || s.toLowerCase() === "europe") {
      isEu = true;
    } else if (s.toUpperCase() === "IN" || s.toLowerCase() === "in india" || s.toLowerCase() === "india") {
      country = "IN";
    } else if (CITY_SLUGS[s.toLowerCase()]) {
      city = CITY_SLUGS[s.toLowerCase()];
    } else {
      city = s.replace(/^in\s+/i, "").toLowerCase();
    }
  }

  if (locId != null && !city) {
    city = CITY_IDS[locId] ?? "";
  }

  if (!country && !isEu && !city && locId == null) {
    return [...locations];
  }

  const matches: LocationItem[] = [];
  const rest: LocationItem[] = [];

  for (const loc of locations) {
    const c = loc.country?.toUpperCase() ?? "";
    const n = (loc.name ?? "").toLowerCase();
    let hit = false;

    if (country) {
      hit = c === country;
    } else if (isEu) {
      hit = c === "GB" || c === "UK" || EU_COUNTRIES.has(c);
    } else if (locId != null && loc.id === locId) {
      hit = true;
    } else if (city && n) {
      if (city.includes("bengaluru") || city.includes("bangalore")) {
        hit = n.includes("bengaluru") || n.includes("bangalore");
      } else if (city.includes("delhi") || city.includes("ncr")) {
        hit = n.includes("delhi") || n.includes("noida") || n.includes("gurugram") || n.includes("gurgaon") || n.includes("ncr");
      } else if (city.includes("mumbai") || city.includes("bombay")) {
        hit = n.includes("mumbai") || n.includes("bombay");
      } else {
        hit = n.includes(city);
      }
    }

    if (hit) matches.push(loc);
    else rest.push(loc);
  }

  return matches.length > 0 ? [...matches, ...rest] : [...locations];
}
