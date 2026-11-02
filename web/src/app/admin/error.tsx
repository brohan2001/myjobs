"use client";

export default function AdminError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="coverage-header">
      <h1 className="coverage-title">Admin API unavailable</h1>
      <p className="coverage-error">{error.message || "The API did not answer."}</p>
      <p className="admin-note">
        Check <code>systemctl --user status myjobs-api</code> on the laptop.{" "}
        <button className="btn-small" onClick={reset}>
          Try again
        </button>
      </p>
    </div>
  );
}
