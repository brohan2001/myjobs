import type { Metadata } from "next";
import Link from "next/link";
import { fetchCoverage } from "@/lib/api";
import { formatAtsName } from "@/lib/ats";
import { relativeTime } from "@/lib/format";
import { Footer } from "@/components/Footer";
import { ThemeToggle } from "@/components/ThemeToggle";

export const revalidate = 30;

export const metadata: Metadata = {
  title: "Coverage - myjobs",
  description: "Where these jobs come from, and how healthy each source is.",
};

export default async function CoveragePage() {
  const coverage = await fetchCoverage();

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

      <main className="coverage-page">
        <Link href="/" className="back-link">
          ← Back to feed
        </Link>

        <div className="coverage-header">
          <h1 className="coverage-title">Coverage</h1>
          <p className="coverage-intro">
            Where these jobs come from, and how healthy each source is.
          </p>
        </div>

        {!coverage ? (
          <p className="coverage-error">Coverage data is currently unavailable.</p>
        ) : (
          <div className="coverage-content">
            <section className="coverage-section">
              <h2 className="coverage-section-title">Sources &amp; ATS health</h2>
              <div className="table-wrap">
                <table className="plain-table">
                  <thead>
                    <tr>
                      <th scope="col">Source / ATS</th>
                      <th scope="col" className="num">Boards</th>
                      <th scope="col" className="num">Healthy</th>
                      <th scope="col" className="num">Failing</th>
                      <th scope="col" className="num">Gone</th>
                      <th scope="col">Last success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverage.by_ats.map((row) => {
                      const humanName = formatAtsName(row.ats);
                      const displayName =
                        humanName === "Career site" && row.ats !== "null"
                          ? `Career site (${row.ats})`
                          : humanName;
                      const timeStr = row.last_success_at
                        ? relativeTime(row.last_success_at)
                        : "never";

                      return (
                        <tr key={row.ats}>
                          <td><b>{displayName}</b></td>
                          <td className="num">{row.boards.toLocaleString("en-US")}</td>
                          <td className="num healthy-cell">{row.healthy.toLocaleString("en-US")}</td>
                          <td className="num failing-cell">
                            {row.failing > 0 ? row.failing.toLocaleString("en-US") : "0"}
                          </td>
                          <td className="num gone-cell">
                            {row.gone > 0 ? row.gone.toLocaleString("en-US") : "0"}
                          </td>
                          <td className="time-cell">{timeStr}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="coverage-section">
              <h2 className="coverage-section-title">Coverage by country</h2>
              <div className="table-wrap">
                <table className="plain-table">
                  <thead>
                    <tr>
                      <th scope="col">Country</th>
                      <th scope="col" className="num">Companies</th>
                      <th scope="col" className="num">Hiring</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverage.by_country.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="empty-cell">
                          No country breakdown available yet.
                        </td>
                      </tr>
                    ) : (
                      coverage.by_country.map((row, idx) => (
                        <tr key={row.country || idx}>
                          <td><b>{row.country.toUpperCase()}</b></td>
                          <td className="num">{row.companies.toLocaleString("en-US")}</td>
                          <td className="num">{row.companies_hiring.toLocaleString("en-US")}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="coverage-section">
              <h2 className="coverage-section-title">India by city</h2>
              <div className="table-wrap">
                <table className="plain-table">
                  <thead>
                    <tr>
                      <th scope="col">City</th>
                      <th scope="col" className="num">Companies</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverage.india_by_city.length === 0 ? (
                      <tr>
                        <td colSpan={2} className="empty-cell">
                          City breakdown being indexed.
                        </td>
                      </tr>
                    ) : (
                      coverage.india_by_city.map((row, idx) => (
                        <tr key={row.city || idx}>
                          <td><b>{row.city}</b></td>
                          <td className="num">{row.companies.toLocaleString("en-US")}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}

        <Footer />
      </main>
    </div>
  );
}
