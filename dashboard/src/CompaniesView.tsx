import { useEffect, useMemo, useState } from "react";
import { api, CompaniesResponse } from "./api";
import { formatCount } from "./format";

export default function CompaniesView({ onShowCompany }: { onShowCompany: (company: string) => void }) {
  const [data, setData] = useState<CompaniesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.companies().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  const needle = filter.trim().toLowerCase();
  const collected = useMemo(
    () => (data?.collected || []).filter((c) => c.company.toLowerCase().includes(needle)).sort((a, b) => b.active_jobs - a.active_jobs),
    [data, needle],
  );
  const linkOnly = (data?.link_only || []).filter((c) => c.company.toLowerCase().includes(needle));

  if (error) return <div className="page"><div className="notice error">Couldn't load companies: {error}</div></div>;
  if (!data) return <div className="page"><p className="muted">Loading companies…</p></div>;

  return (
    <div className="page">
      <input className="search narrow" type="search" placeholder="Find a company…" value={filter}
        onChange={(e) => setFilter(e.target.value)} aria-label="Find a company" />

      <section>
        <h2>Collected automatically <span className="muted">({data.collected.length})</span></h2>
        <p className="muted">Open jobs are read from these companies' official careers sites every few hours.</p>
        <ul className="company-grid">
          {collected.map((c) => (
            <li key={c.company}>
              <button className="company-card" onClick={() => onShowCompany(c.company)}>
                <span className="company-name">{c.company}</span>
                <span className="company-count">{formatCount(c.active_jobs)} open {c.active_jobs === 1 ? "job" : "jobs"}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Check these yourself <span className="muted">({data.link_only.length})</span></h2>
        <p className="muted">
          These companies block automated access or have no public job feed, so their jobs can't be listed here. Their
          careers pages are one click away.
        </p>
        <ul className="company-grid">
          {linkOnly.map((c) => (
            <li key={c.company} className="company-card static">
              <span className="company-name">{c.company}</span>
              <span className="muted small">{c.reason}</span>
              <span className="company-links">
                <a href={c.careers_url} target="_blank" rel="noopener noreferrer">Careers page ↗</a>
                {c.fresher_url && <a href={c.fresher_url} target="_blank" rel="noopener noreferrer">Freshers / campus ↗</a>}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
