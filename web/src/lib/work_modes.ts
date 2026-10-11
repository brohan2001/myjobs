const MODE_MAP: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
  "on-site": "On-site",
  on_site: "On-site",
  in_office: "On-site",
};

export function formatWorkModes(
  workModes?: (string | null | undefined)[] | null
): string {
  if (!workModes?.length) return "";

  const parts: string[] = [];
  for (const m of workModes) {
    if (!m || typeof m !== "string") continue;
    const k = m.trim().toLowerCase();
    if (!k || k === "undefined" || k === "null") continue;
    const label = MODE_MAP[k] ?? (k.charAt(0).toUpperCase() + k.slice(1));
    if (!parts.includes(label)) parts.push(label);
  }

  return parts.join(" / ");
}
