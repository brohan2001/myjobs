import Link from "next/link";
import { adminFetch, type ErrorGroup } from "@/lib/admin";
import { formatAtsName } from "@/lib/ats";

export default async function AdminErrors() {
  const { errors } = await adminFetch<{ errors: ErrorGroup[] }>("/errors");

  return (
    <>
      <div className="coverage-header">
        <h1 className="coverage-title">Errors</h1>
        <p className="coverage-intro">
          Failing and auto-disabled boards, grouped by their last error. A board is disabled after 5 failures in a row.
        </p>
      </div>
      <div className="table-wrap">
        <table className="plain-table">
          <thead>
            <tr>
              <th scope="col" className="num">Boards</th>
              <th scope="col">Error</th>
              <th scope="col">ATS</th>
            </tr>
          </thead>
          <tbody>
            {errors.length === 0 && (
              <tr>
                <td colSpan={3} className="empty-cell">
                  No failing boards.
                </td>
              </tr>
            )}
            {errors.map((e) => (
              <tr key={e.error}>
                <td className="num failing-cell">{e.boards}</td>
                <td className="error-cell">{e.error}</td>
                <td>
                  {e.ats.map((a, i) => (
                    <span key={a ?? i}>
                      {i > 0 && ", "}
                      <Link href={`/admin/boards?ats=${encodeURIComponent(a ?? "")}&sort=failures`}>
                        {formatAtsName(a ?? "null")}
                      </Link>
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
