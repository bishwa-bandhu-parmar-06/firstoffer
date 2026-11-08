import { useEffect, useState } from "react";
import { api, SourceHealth } from "./api";
import { formatCount, relativeDate } from "./format";

export default function SourcesView() {
  const [sources, setSources] = useState<SourceHealth[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sources().then(setSources).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="page"><div className="notice error">Couldn't load sources: {error}</div></div>;
  if (!sources) return <div className="page"><p className="muted">Loading sources…</p></div>;

  const failing = sources.filter((s) => s.consecutive_failures > 0).length;
  return (
    <div className="page">
      <h2>Source health</h2>
      <p className="muted">
        {sources.length} job boards polled · {failing === 0 ? "all working" : `${failing} failing`}. Failing sources are listed first.
      </p>
      <div className="table-wrap">
        <table className="sources">
          <thead>
            <tr><th>Company</th><th>Platform</th><th className="num">Jobs</th><th>Last success</th><th>Status</th></tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.key} className={s.consecutive_failures ? "failing" : undefined}>
                <td>{s.company}</td>
                <td><code>{s.provider}</code></td>
                <td className="num">{formatCount(s.last_job_count)}{s.complete_listing ? "" : "+"}</td>
                <td>{relativeDate(s.last_success_at) || "Never"}</td>
                <td>
                  {s.consecutive_failures
                    ? <span className="status bad" title={s.last_error || ""}>Failing ×{s.consecutive_failures}</span>
                    : <span className="status ok">OK</span>}
                  {!s.complete_listing && <span className="muted small"> partial listing</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
