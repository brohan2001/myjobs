const ATS_HUMAN_NAMES: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
};

const CAREER_SITE_SOURCES = new Set([
  "dom",
  "sitemap",
  "nextdata",
  "api_sniffer",
  "inline",
]);

export function formatAtsName(ats: string | null | undefined): string {
  if (!ats || typeof ats !== "string") {
    return "Career site";
  }

  const normalized = ats.trim().toLowerCase();
  if (!normalized || normalized === "null" || normalized === "undefined") {
    return "Career site";
  }

  if (CAREER_SITE_SOURCES.has(normalized)) {
    return "Career site";
  }

  return ATS_HUMAN_NAMES[normalized] ?? "Career site";
}
