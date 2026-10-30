import Link from "next/link";
import { adminFetch, since, type Board } from "@/lib/admin";
import { formatAtsName } from "@/lib/ats";
import { disableBoard, enableBoard, recrawlBoard } from "../actions";

const STATUSES = ["all", "failing", "overdue", "never", "disabled", "gone"];
const SORTS: Record<string, string> = {
  stale: "Least recently successful",
  recent: "Most recently crawled",
  due: "Next due",
  failures: "Most failures",
};

type Params = { q?: string; ats?: string; status?: string; sort?: string; page?: string };

function statusOf(b: Board): string {
  if (!b.is_enabled && b.board_status !== "gone") return "disabled";
  if (b.consecutive_failures > 0) return `failing ×${b.consecutive_failures}`;
  return b.board_status;
}

export default async function AdminBoards({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const status = STATUSES.includes(params.status ?? "") ? params.status! : "all";
  const sort = params.sort && params.sort in SORTS ? params.sort : "stale";
  const page = Math.max(1, Number(params.page) || 1);
  const query = new URLSearchParams({ status, sort, page: String(page) });
  if (params.q) query.set("q", params.q);
  if (params.ats) query.set("ats", params.ats);
  const { boards, has_more } = await adminFetch<{ boards: Board[]; has_more: boolean }>(`/boards?${query}`);
  const pageHref = (p: number) => {
    const next = new URLSearchParams(query);
    next.set("page", String(p));
    return `/admin/boards?${next}`;
  };

  return (
    <>
      <div className="coverage-header">
        <h1 className="coverage-title">Boards</h1>
        <p className="coverage-intro">When each career board was last crawled, when it&apos;s due next, and why it failed.</p>
      </div>

      <form className="admin-filters" method="get">
        <input name="q" defaultValue={params.q} placeholder="Company, board or ATS" aria-label="Search" />
        <input name="ats" defaultValue={params.ats} placeholder="ATS (e.g. greenhouse)" aria-label="ATS" />
        <select name="status" defaultValue={status} aria-label="Status">
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select name="sort" defaultValue={sort} aria-label="Sort">
          {Object.entries(SORTS).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <button className="tbtn" type="submit">
          Filter
        </button>
      </form>

      <div className="table-wrap">
        <table className="plain-table">
          <thead>
            <tr>
              <th scope="col">Board</th>
              <th scope="col">ATS</th>
              <th scope="col">Status</th>
              <th scope="col">Last crawled</th>
              <th scope="col">Last success</th>
              <th scope="col">Next check</th>
              <th scope="col" className="num">Jobs</th>
              <th scope="col">Last error</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {boards.length === 0 && (
              <tr>
                <td colSpan={9} className="empty-cell">
                  No boards match.
                </td>
              </tr>
            )}
            {boards.map((b) => {
              const state = statusOf(b);
              return (
                <tr key={b.id}>
                  <td>
                    <b>{b.company_name}</b>
                    <br />
                    <a className="admin-note" href={b.board_url} target="_blank" rel="noopener noreferrer">
                      {b.board_slug ?? b.board_url}
                    </a>
                  </td>
                  <td>{formatAtsName(b.crawler_type ?? "null")}</td>
                  <td className={state.startsWith("failing") ? "failing-cell" : state === "active" ? "healthy-cell" : "gone-cell"}>
                    {state}
                  </td>
                  <td className="time-cell">{since(b.last_checked_at)}</td>
                  <td className="time-cell">{since(b.last_success_at)}</td>
                  <td className="time-cell">{b.is_enabled ? since(b.next_check_at) : "–"}</td>
                  <td className="num">{b.active_jobs}</td>
                  <td className="error-cell" title={b.last_error ?? undefined}>
                    {b.consecutive_failures > 0 || !b.is_enabled ? b.last_error?.slice(0, 90) : ""}
                  </td>
                  <td className="actions-cell">
                    {b.is_enabled ? (
                      <>
                        <form action={recrawlBoard}>
                          <input type="hidden" name="id" value={b.id} />
                          <button className="btn-small" type="submit">
                            Recrawl
                          </button>
                        </form>
                        <form action={disableBoard}>
                          <input type="hidden" name="id" value={b.id} />
                          <button className="btn-small" type="submit">
                            Disable
                          </button>
                        </form>
                      </>
                    ) : (
                      <form action={enableBoard}>
                        <input type="hidden" name="id" value={b.id} />
                        <button className="btn-small" type="submit">
                          Enable
                        </button>
                      </form>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <nav className="pager" aria-label="Pages">
        {page > 1 && <Link href={pageHref(page - 1)}>← Previous</Link>}
        <span className="admin-note">Page {page}</span>
        {has_more && <Link href={pageHref(page + 1)}>Next →</Link>}
      </nav>
    </>
  );
}
