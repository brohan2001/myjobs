import Link from "next/link";
import { AutoRefresh } from "@/components/AutoRefresh";
import { adminFetch, bytes, duration, since, type Overview, type Service, type SystemStats } from "@/lib/admin";

function Meter({ percent, label }: { percent: number | null; label: string }) {
  const p = Math.max(0, Math.min(100, percent ?? 0));
  return (
    <span className="meter" role="img" aria-label={label} title={label}>
      <span className={p >= 90 ? "hot" : undefined} style={{ width: `${p}%` }} />
    </span>
  );
}

function Tile({ value, label, warn }: { value: string; label: string; warn?: boolean }) {
  return (
    <div className="tile">
      <div className={warn ? "tile-num failing-cell" : "tile-num"}>{value}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}

const n = (x: number) => x.toLocaleString("en-US");

export default async function AdminOverview() {
  const [overview, system] = await Promise.all([
    adminFetch<Overview>("/overview"),
    adminFetch<SystemStats>("/system").catch(() => null),
  ]);
  const { stats, health, queues, backup } = overview;
  const budget = system?.services.find((s) => s.unit === "myjobs.slice");
  const services = system?.services.filter((s) => s.unit !== "myjobs.slice") ?? [];
  const host = system?.host;
  const feedAge = health.feed_age_minutes;

  return (
    <>
      <AutoRefresh seconds={15} />
      <div className="coverage-header">
        <h1 className="coverage-title">Overview</h1>
        <p className="coverage-intro">Crawl health, queues and what the laptop is spending. Refreshes every 15 s.</p>
      </div>

      <div className="tiles">
        <Tile value={n(stats.active_jobs)} label="active tech jobs" />
        <Tile value={n(stats.new_last_24h)} label="new in 24 h" />
        <Tile value={`${n(stats.boards_fresh_24h)} / ${n(stats.boards_enabled)}`} label="boards crawled OK in 24 h" />
        <Tile value={n(stats.boards_failing)} label="boards failing" warn={stats.boards_failing > 0} />
        <Tile value={n(health.overdue_boards)} label="boards >2 h overdue" warn={health.overdue_boards > 0} />
        <Tile
          value={feedAge == null ? "–" : feedAge < 120 ? `${Math.round(feedAge)} min` : `${(feedAge / 60).toFixed(1)} h`}
          label="since the newest posting"
          warn={feedAge == null || feedAge > 180}
        />
      </div>

      <section className="coverage-section">
        <h2 className="coverage-section-title">Health checks</h2>
        {health.alerts.length === 0 ? (
          <p className="healthy-text">All checks pass (same checks as <code>myjobs health</code>).</p>
        ) : (
          <ul className="alert-list">
            {health.alerts.map((a) => (
              <li key={a.check + a.message}>
                <b>{a.check}</b>: {a.message}
              </li>
            ))}
          </ul>
        )}
        <p className="admin-note">
          Last crawl success {since(stats.last_updated)} · {n(health.gone_last_day)} boards marked gone in 24 h ·{" "}
          <Link href="/admin/boards?status=failing&sort=failures">failing boards</Link> ·{" "}
          <Link href="/admin/errors">errors by cause</Link>
        </p>
      </section>

      <section className="coverage-section">
        <h2 className="coverage-section-title">Resources</h2>
        {!system || !host ? (
          <p className="coverage-error">Resource stats are unavailable.</p>
        ) : (
          <>
            {budget && (
              <p className="admin-note">
                Budget (myjobs.slice): CPU {budget.cpu_percent ?? "–"}% of {budget.cpu_quota_percent ?? "∞"}%{" "}
                <Meter
                  percent={budget.cpu_quota_percent ? (100 * (budget.cpu_percent ?? 0)) / budget.cpu_quota_percent : null}
                  label="CPU used of budget"
                />{" "}
                · memory {bytes(budget.memory_bytes)} of {bytes(budget.memory_max_bytes)}{" "}
                <Meter
                  percent={budget.memory_max_bytes ? (100 * (budget.memory_bytes ?? 0)) / budget.memory_max_bytes : null}
                  label="memory used of budget"
                />{" "}
                · Postgres and Redis have their own limits below.
              </p>
            )}
            <div className="table-wrap">
              <table className="plain-table">
                <thead>
                  <tr>
                    <th scope="col">Service</th>
                    <th scope="col">State</th>
                    <th scope="col" className="num">Up</th>
                    <th scope="col" className="num">Restarts</th>
                    <th scope="col" className="num">CPU</th>
                    <th scope="col" className="num">Memory (peak)</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((s: Service) => (
                    <tr key={s.unit}>
                      <td>
                        <b>{s.unit.replace(/^myjobs-|\.service$/g, "")}</b>
                      </td>
                      <td className={s.state === "active" || s.unit.includes("backup") ? "healthy-cell" : "failing-cell"}>
                        {s.state}
                        {s.sub_state && s.sub_state !== s.state ? ` (${s.sub_state})` : ""}
                      </td>
                      <td className="num">{s.state === "active" ? duration(s.uptime_s) : "–"}</td>
                      <td className={s.restarts ? "num failing-cell" : "num"}>{s.restarts ?? "–"}</td>
                      <td className="num">{s.cpu_percent == null ? "–" : `${s.cpu_percent}%`}</td>
                      <td className="num">
                        {bytes(s.memory_bytes)} ({bytes(s.memory_peak_bytes)})
                        {s.memory_max_bytes ? ` / ${bytes(s.memory_max_bytes)}` : ""}
                      </td>
                    </tr>
                  ))}
                  {system.containers.map((c) => (
                    <tr key={c.name}>
                      <td>
                        <b>{c.name.replace(/^myjobs-|-1$/g, "")}</b> <span className="admin-note">docker</span>
                      </td>
                      <td className="healthy-cell">running</td>
                      <td className="num">–</td>
                      <td className="num">–</td>
                      <td className="num">{c.cpu_percent}</td>
                      <td className="num">{c.memory}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="table-wrap">
              <table className="plain-table">
                <tbody>
                  <tr>
                    <th scope="row">CPU ({host.cpu_count} threads)</th>
                    <td>
                      <span className="core-bars">
                        {host.cpu_percent_per_core.map((p, i) => (
                          <Meter key={i} percent={p} label={`thread ${i}: ${p}%`} />
                        ))}
                      </span>{" "}
                      load {host.load_avg.join(" / ")}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Temperature</th>
                    <td className={host.cpu_temp_c != null && host.cpu_temp_c >= 85 ? "failing-cell" : undefined}>
                      {host.cpu_temp_c == null ? "–" : `${Math.round(host.cpu_temp_c)} °C`}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Memory</th>
                    <td>
                      {bytes(host.memory.used)} of {bytes(host.memory.total)}{" "}
                      <Meter percent={host.memory.percent} label="memory" /> · swap {bytes(host.swap.used)} of{" "}
                      {bytes(host.swap.total)}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Disk</th>
                    <td>
                      {bytes(host.disk.used)} of {bytes(host.disk.total)} <Meter percent={host.disk.percent} label="disk" />
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">GPU (Iris Xe)</th>
                    <td>
                      {host.gpu ? `${host.gpu.freq_mhz} of ${host.gpu.max_mhz} MHz` : "–"}
                      <span className="admin-note"> · nothing in myjobs uses the GPU; crawling is network and CPU work</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="coverage-section">
        <h2 className="coverage-section-title">Queues and backups</h2>
        <div className="table-wrap">
          <table className="plain-table">
            <thead>
              <tr>
                <th scope="col">Pipeline</th>
                <th scope="col" className="num">Domains ready now</th>
                <th scope="col" className="num">In flight</th>
                <th scope="col" className="num">Dead-lettered</th>
              </tr>
            </thead>
            <tbody>
              {queues ? (
                (["simple", "browser"] as const).map((w) => (
                  <tr key={w}>
                    <td>
                      <b>{w === "simple" ? "HTTP" : "Browser"}</b>
                    </td>
                    <td className="num">{n(queues[w].ready_now)}</td>
                    <td className="num">{n(queues[w].inflight)}</td>
                    <td className={queues[w].deadletter ? "num failing-cell" : "num"}>{n(queues[w].deadletter)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="empty-cell">
                    Redis is unreachable.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="admin-note">
          {backup
            ? `Latest backup: ${backup.file}, ${bytes(backup.bytes)}, ${since(backup.at)}.`
            : "No backups in ~/backups yet (the nightly timer runs at 03:30)."}
        </p>
      </section>
    </>
  );
}
