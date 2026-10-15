import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchJob } from "@/lib/api";
import { formatAtsName } from "@/lib/ats";
import { formatSalary, relativeTime } from "@/lib/format";
import { RATES } from "@/lib/rates";
import { formatWorkModes } from "@/lib/work_modes";
import { Footer } from "@/components/Footer";
import { ThemeToggle } from "@/components/ThemeToggle";

export const revalidate = 30;

interface JobDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function JobDetailPage({ params }: JobDetailPageProps) {
  const { id } = await params;

  let job = null;
  try {
    job = await fetchJob(id);
  } catch {
    // If API error or not found
    job = null;
  }

  if (!job) {
    notFound();
  }

  const timeString = relativeTime(job.listed_at);
  const atsName = formatAtsName(job.ats);

  // Formatted location
  let locationText = "Remote";
  if (job.locations && job.locations.length > 0) {
    const valid = job.locations.filter((l) => l.name);
    if (valid.length > 0) {
      locationText = valid.map((l) => l.name).join("; ");
    } else if (job.locations_raw && job.locations_raw.length > 0) {
      locationText = job.locations_raw.join("; ");
    }
  } else if (job.locations_raw && job.locations_raw.length > 0) {
    locationText = job.locations_raw.join("; ");
  }

  const modesText = formatWorkModes(job.work_modes);

  const salaryText = formatSalary(job.salary, "native", RATES);

  return (
    <div className="wrap">
      <header>
        <div className="top">
          <p className="brand">
            <Link href="/">myjobs</Link>
          </p>
          <ThemeToggle />
        </div>
      </header>

      <main className="detail">
        <Link href="/" className="back-link">
          ← Back to feed
        </Link>

        <div className="detail-header">
          <p className="when">{job.posted_at ? "posted" : "first seen"} {timeString}</p>
          <h1 className="detail-title">{job.title}</h1>
          <p className="detail-meta">
            <b>{job.company.name}</b> in {locationText}
          </p>
          <p className="detail-tags">
            {modesText && <span className="mode">{modesText}</span>}
            {salaryText && <span className="pay">{salaryText}</span>}
            {atsName && <span>via {atsName}</span>}
          </p>
          <div className="detail-actions">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
            >
              Apply on company site
            </a>
          </div>
        </div>

        {job.description_html ? (
          <div
            className="detail-body"
            dangerouslySetInnerHTML={{ __html: job.description_html }}
          />
        ) : (
          <p className="detail-body">
            No description provided. Click &quot;Apply on company site&quot; to view full details on the employer&apos;s site.
          </p>
        )}
      </main>
      <Footer />
    </div>
  );
}
