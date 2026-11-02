const ATS_MAP: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
};

export function formatAtsName(ats: string | null | undefined): string {
  if (!ats) return "Career site";
  const k = ats.trim().toLowerCase();
  if (k === "null" || k === "undefined") return "Career site";
  return ATS_MAP[k] ?? "Career site";
}
