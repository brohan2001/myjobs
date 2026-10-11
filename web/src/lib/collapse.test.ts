import { describe, expect, it } from "vitest";
import { collapseRuns } from "./collapse";
import { Job } from "./types";

function makeJob(
  id: string,
  companySlug: string,
  companyName: string,
  firstSeenAt = "2026-10-11T12:00:00Z"
): Job {
  return {
    id,
    title: `Role ${id}`,
    url: `https://example.com/jobs/${id}`,
    company: {
      slug: companySlug,
      name: companyName,
      website: `https://${companySlug}.com`,
      logo: null,
    },
    locations: [],
    locations_raw: ["Bengaluru"],
    work_modes: ["hybrid"],
    employment_type: "full-time",
    salary: null,
    ats: "greenhouse",
    first_seen_at: firstSeenAt,
    last_seen_at: firstSeenAt,
  };
}

describe("collapseRuns", () => {
  it("case 1: no runs (less than 3 consecutive or distinct companies)", () => {
    const jobs = [
      makeJob("1", "acme", "Acme"),
      makeJob("2", "acme", "Acme"),
      makeJob("3", "beta", "Beta"),
      makeJob("4", "gamma", "Gamma"),
    ];
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(4);
    expect(result.every((item) => item.kind === "job")).toBe(true);
    expect((result[0] as { kind: "job"; job: Job }).job.id).toBe("1");
    expect((result[1] as { kind: "job"; job: Job }).job.id).toBe("2");
    expect((result[2] as { kind: "job"; job: Job }).job.id).toBe("3");
    expect((result[3] as { kind: "job"; job: Job }).job.id).toBe("4");
  });

  it("case 2: a run of exactly 3", () => {
    const jobs = [
      makeJob("1", "kotak", "Kotak Mahindra Bank"),
      makeJob("2", "kotak", "Kotak Mahindra Bank"),
      makeJob("3", "kotak", "Kotak Mahindra Bank"),
    ];
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual({ kind: "job", job: jobs[0] });
    expect(result[1]).toEqual({ kind: "job", job: jobs[1] });
    expect(result[2]).toEqual({
      kind: "more",
      company: { slug: "kotak", name: "Kotak Mahindra Bank" },
      count: 1,
      hidden: [jobs[2]],
    });
  });

  it("case 3: a long run (e.g. 50 jobs from Kotak Mahindra Bank)", () => {
    const jobs = Array.from({ length: 50 }, (_, i) =>
      makeJob(String(i + 1), "kotak", "Kotak Mahindra Bank")
    );
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(3); // 2 kept + 1 more item
    expect(result[0]).toEqual({ kind: "job", job: jobs[0] });
    expect(result[1]).toEqual({ kind: "job", job: jobs[1] });
    expect(result[2]).toEqual({
      kind: "more",
      company: { slug: "kotak", name: "Kotak Mahindra Bank" },
      count: 48,
      hidden: jobs.slice(2),
    });
  });

  it("case 4: two separate runs from same and different companies", () => {
    const jobs = [
      makeJob("a1", "acme", "Acme"),
      makeJob("a2", "acme", "Acme"),
      makeJob("a3", "acme", "Acme"),
      makeJob("b1", "beta", "Beta"),
      makeJob("a4", "acme", "Acme"),
      makeJob("a5", "acme", "Acme"),
      makeJob("a6", "acme", "Acme"),
    ];
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(7);
    // Run 1: a1, a2, more(count: 1)
    expect(result[0]).toEqual({ kind: "job", job: jobs[0] });
    expect(result[1]).toEqual({ kind: "job", job: jobs[1] });
    expect(result[2]).toEqual({
      kind: "more",
      company: { slug: "acme", name: "Acme" },
      count: 1,
      hidden: [jobs[2]],
    });
    // Single b1
    expect(result[3]).toEqual({ kind: "job", job: jobs[3] });
    // Run 2: a4, a5, more(count: 1)
    expect(result[4]).toEqual({ kind: "job", job: jobs[4] });
    expect(result[5]).toEqual({ kind: "job", job: jobs[5] });
    expect(result[6]).toEqual({
      kind: "more",
      company: { slug: "acme", name: "Acme" },
      count: 1,
      hidden: [jobs[6]],
    });
  });

  it("case 5: keep=1", () => {
    const jobs = [
      makeJob("1", "acme", "Acme"),
      makeJob("2", "acme", "Acme"),
      makeJob("3", "acme", "Acme"),
    ];
    const result = collapseRuns(jobs, 1);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({ kind: "job", job: jobs[0] });
    expect(result[1]).toEqual({
      kind: "more",
      company: { slug: "acme", name: "Acme" },
      count: 2,
      hidden: [jobs[1], jobs[2]],
    });
  });

  it("case 6: an empty list", () => {
    const result = collapseRuns([]);
    expect(result).toEqual([]);
  });

  it("case 7: a run at the end", () => {
    const jobs = [
      makeJob("1", "other", "Other"),
      makeJob("2", "acme", "Acme"),
      makeJob("3", "acme", "Acme"),
      makeJob("4", "acme", "Acme"),
      makeJob("5", "acme", "Acme"),
    ];
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(4);
    expect(result[0]).toEqual({ kind: "job", job: jobs[0] });
    expect(result[1]).toEqual({ kind: "job", job: jobs[1] });
    expect(result[2]).toEqual({ kind: "job", job: jobs[2] });
    expect(result[3]).toEqual({
      kind: "more",
      company: { slug: "acme", name: "Acme" },
      count: 2,
      hidden: [jobs[3], jobs[4]],
    });
  });

  it("case 8: interleaved companies", () => {
    const jobs = [
      makeJob("1", "a", "Company A"),
      makeJob("2", "b", "Company B"),
      makeJob("3", "a", "Company A"),
      makeJob("4", "b", "Company B"),
      makeJob("5", "a", "Company A"),
      makeJob("6", "b", "Company B"),
    ];
    const result = collapseRuns(jobs);
    expect(result).toHaveLength(6);
    expect(result.every((item) => item.kind === "job")).toBe(true);
    expect(result.map((item) => (item as { kind: "job"; job: Job }).job.id)).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
    ]);
  });

  it("respects time bucket boundaries", () => {
    // 2 jobs in "last hour" (diffSec <= 3600) and 2 jobs in "yesterday"
    const now = new Date("2026-10-11T12:00:00Z");
    const lastHourTime = new Date("2026-10-11T11:45:00Z").toISOString();
    const yesterdayTime = new Date("2026-10-10T11:45:00Z").toISOString();

    const jobs = [
      makeJob("1", "kotak", "Kotak", lastHourTime),
      makeJob("2", "kotak", "Kotak", lastHourTime),
      makeJob("3", "kotak", "Kotak", yesterdayTime),
      makeJob("4", "kotak", "Kotak", yesterdayTime),
    ];
    // Each bucket has 2 jobs; neither bucket reaches 3, so none collapse across the bucket boundary
    const result = collapseRuns(jobs, 2, now);
    expect(result).toHaveLength(4);
    expect(result.every((item) => item.kind === "job")).toBe(true);

    // If bucket 1 has 3 jobs and bucket 2 has 3 jobs, each collapses independently
    const jobs6 = [
      makeJob("1", "kotak", "Kotak", lastHourTime),
      makeJob("2", "kotak", "Kotak", lastHourTime),
      makeJob("3", "kotak", "Kotak", lastHourTime),
      makeJob("4", "kotak", "Kotak", yesterdayTime),
      makeJob("5", "kotak", "Kotak", yesterdayTime),
      makeJob("6", "kotak", "Kotak", yesterdayTime),
    ];
    const result6 = collapseRuns(jobs6, 2, now);
    expect(result6).toHaveLength(6); // 2 jobs + 1 more from lastHour, 2 jobs + 1 more from yesterday
    expect(result6[2].kind).toBe("more");
    expect(result6[5].kind).toBe("more");
  });

  it("handles page boundaries when loading more pages", () => {
    // Page 1 has 2 jobs from Acme
    const page1 = [makeJob("1", "acme", "Acme"), makeJob("2", "acme", "Acme")];
    const result1 = collapseRuns(page1);
    expect(result1).toHaveLength(2);

    // Page 2 adds 3 more jobs from Acme
    const page2 = [
      makeJob("3", "acme", "Acme"),
      makeJob("4", "acme", "Acme"),
      makeJob("5", "acme", "Acme"),
    ];
    const accumulated = [...page1, ...page2];
    const result2 = collapseRuns(accumulated);
    expect(result2).toHaveLength(3); // 2 kept + 1 more item (count: 3)
    expect(result2[2]).toEqual({
      kind: "more",
      company: { slug: "acme", name: "Acme" },
      count: 3,
      hidden: page2,
    });
  });
});
