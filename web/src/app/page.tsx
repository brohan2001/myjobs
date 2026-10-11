import { fetchJobs, fetchStats } from "@/lib/api";
import { PLACES } from "@/lib/constants";
import { Job, Stats } from "@/lib/types";
import { FeedClient } from "@/components/FeedClient";
import { Footer } from "@/components/Footer";

export const revalidate = 30;

interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function FeedPage({ searchParams }: PageProps) {
  const params = await searchParams;

  const rawCountry = typeof params.country === "string" ? params.country : undefined;
  const rawLocation = typeof params.location === "string" ? params.location : undefined;
  const rawWorkMode = typeof params.work_mode === "string" ? params.work_mode : undefined;
  const rawSince = typeof params.since === "string" ? params.since : "24h";
  const rawQ = typeof params.q === "string" ? params.q : undefined;
  const rawCursor = typeof params.cursor === "string" ? params.cursor : undefined;
  const rawCompany = typeof params.company === "string" ? params.company : undefined;

  // Determine effective country and location
  // Default region is India (country=IN) unless specified or location specified
  let effectiveCountry: string | undefined = rawCountry;
  let effectiveLocation: string | undefined = rawLocation;

  if (!rawLocation && !rawCountry) {
    effectiveCountry = "IN";
  } else if (rawCountry === "all") {
    effectiveCountry = undefined;
  }

  let initialJobs: Job[] = [];
  let initialNextCursor: string | null = null;
  let initialError = false;
  let stats: Stats | null = null;

  try {
    const [jobsRes, statsRes] = await Promise.all([
      fetchJobs({
        country: effectiveCountry,
        location: effectiveLocation,
        work_mode: rawWorkMode,
        company: rawCompany,
        since: rawSince,
        q: rawQ,
        cursor: rawCursor,
      }),
      fetchStats(),
    ]);

    initialJobs = jobsRes.jobs;
    initialNextCursor = jobsRes.next_cursor;
    stats = statsRes;
  } catch {
    initialError = true;
  }

  return (
    <>
      <a className="skip" href="#list">
        Skip to the list
      </a>
      <FeedClient
        initialJobs={initialJobs}
        initialNextCursor={initialNextCursor}
        initialStats={stats}
        initialError={initialError}
        footer={<Footer />}
      />
    </>
  );
}
