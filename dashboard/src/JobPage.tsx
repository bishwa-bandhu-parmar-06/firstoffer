// Full page for one job at /job/:id — what people land on when someone shares a job with them.
import { useEffect, useState } from "react";
import { api, EMPTY_QUERY, JobDetail, JobSummary } from "./api";
import JobDetailBody from "./JobDetail";
import { place } from "./format";

export default function JobPage({ id, telegramUrl }: { id: number; telegramUrl: string | null }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState<JobSummary[]>([]);

  useEffect(() => {
    setJob(null);
    setError(null);
    window.scrollTo(0, 0);
    api.job(id)
      .then((j) => {
        setJob(j);
        document.title = `${j.title} at ${j.company} · FirstOffer`;
        return api.jobs({ ...EMPTY_QUERY, company: [j.company] }, 0, 7);
      })
      .then((page) => setMore(page.items.filter((m) => m.id !== id).slice(0, 6)))
      .catch((e: Error) => setError(e.message.includes("404") ? "not-found" : e.message));
  }, [id]);

  return (
    <div className="page job-page">
      <a className="back-link" href="/">← All jobs</a>
      <div className="job-page-grid">
        <article className="job-page-main">
          {error === "not-found" && (
            <div className="notice">
              This job isn't on FirstOffer any more; it has probably closed. <a href="/">Browse open jobs</a>.
            </div>
          )}
          {error && error !== "not-found" && <div className="notice error">Couldn't load this job: {error}</div>}
          {!job && !error && <div className="skeleton tall" />}
          {job && <JobDetailBody job={job} headingLevel={1} />}
        </article>
        <aside className="job-page-side">
          {job && more.length > 0 && (
            <section className="side-card">
              <h2>More at {job.company}</h2>
              <ul className="mini-jobs">
                {more.map((m) => (
                  <li key={m.id}>
                    <a href={`/job/${m.id}`}>{m.title}</a>
                    <span className="muted small">{place(m)}</span>
                  </li>
                ))}
              </ul>
              <a className="link-button" href={`/?company=${encodeURIComponent(job.company)}`}>All {job.company} jobs →</a>
            </section>
          )}
          {telegramUrl && (
            <section className="side-card telegram-card">
              <h2>Get jobs like this first</h2>
              <p className="muted small">New fresher-friendly IT jobs are posted to our Telegram channel every hour.</p>
              <a className="telegram-button" href={telegramUrl} target="_blank" rel="noopener noreferrer">Join on Telegram</a>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
