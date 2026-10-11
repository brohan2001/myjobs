import { timeBucket } from "./format";
import { Job } from "./types";

export type CollapsedItem =
  | { kind: "job"; job: Job }
  | {
      kind: "more";
      company: { slug: string; name: string };
      count: number;
      hidden: Job[];
    };

function getBucket(job: Job, now?: Date): string | null {
  if (!job.first_seen_at) return null;
  try {
    return timeBucket(job.first_seen_at, now);
  } catch {
    return null;
  }
}

function sameRun(a: Job, b: Job, now?: Date): boolean {
  const aSlug = a.company?.slug;
  const bSlug = b.company?.slug;
  if (!aSlug || !bSlug || aSlug !== bSlug) {
    return false;
  }

  const aBucket = getBucket(a, now);
  const bBucket = getBucket(b, now);
  if (aBucket !== null && bBucket !== null) {
    return aBucket === bBucket;
  }

  return true;
}

export function collapseRuns(
  jobs: Job[],
  keep = 2,
  now?: Date
): Array<
  | { kind: "job"; job: Job }
  | {
      kind: "more";
      company: { slug: string; name: string };
      count: number;
      hidden: Job[];
    }
> {
  if (!jobs || jobs.length === 0) {
    return [];
  }

  const effectiveKeep = Math.max(0, keep);
  const result: CollapsedItem[] = [];

  let i = 0;
  while (i < jobs.length) {
    let j = i + 1;
    while (j < jobs.length && sameRun(jobs[i], jobs[j], now)) {
      j++;
    }

    const runLength = j - i;
    const run = jobs.slice(i, j);

    if (runLength >= 3 && runLength > effectiveKeep) {
      for (let k = 0; k < effectiveKeep; k++) {
        result.push({ kind: "job", job: run[k] });
      }
      const hidden = run.slice(effectiveKeep);
      result.push({
        kind: "more",
        company: {
          slug: run[0].company.slug,
          name: run[0].company.name,
        },
        count: hidden.length,
        hidden,
      });
    } else {
      for (const job of run) {
        result.push({ kind: "job", job });
      }
    }

    i = j;
  }

  return result;
}
