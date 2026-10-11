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
  if (!workModes || !Array.isArray(workModes) || workModes.length === 0) {
    return "";
  }

  const parts: string[] = [];

  for (const m of workModes) {
    if (!m || typeof m !== "string") continue;
    const key = m.trim().toLowerCase();
    if (!key || key === "undefined" || key === "null") continue;

    const label = MODE_MAP[key] ?? (key.charAt(0).toUpperCase() + key.slice(1));
    if (label && !parts.includes(label)) {
      parts.push(label);
    }
  }

  return parts.join(" / ");
}
