import { JobSummary } from "./api";
import { ApplyButton, SaveButton, ShareButton } from "./actions";
import { EXPERIENCE_SHORT, isNew, place, relativeDate } from "./format";
import { STATUS_LABELS, useTrackedJob } from "./store";

export function ExperienceBadge({ level }: { level: string | null }) {
  if (!level) return null;
  return <span className={`badge level-${level}`}>{EXPERIENCE_SHORT[level] || level}</span>;
}

export default function JobCard({ job, selected, onOpen }: { job: JobSummary; selected: boolean; onOpen: () => void }) {
  const posted = relativeDate(job.posted_at);
  const tracked = useTrackedJob(job.id);
  return (
    <li className={selected ? "job-card selected" : "job-card"}>
      <div className="job-main">
        <div className="job-title-row">
          {/* A real link, so it can be opened in a new tab or copied; a plain click opens the side panel. */}
          <a className="job-title" href={`/job/${job.id}`}
            onClick={(e) => { if (!e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) { e.preventDefault(); onOpen(); } }}>
            {job.title}
          </a>
          {isNew(job.first_seen_at) && <span className="badge new">New</span>}
          {tracked && tracked.status !== "saved" && <span className="badge tracked">{STATUS_LABELS[tracked.status]}</span>}
        </div>
        <p className="job-company">{job.company}</p>
        <p className="job-meta">
          <span>{place(job)}</span>
          {job.is_remote && <span className="badge remote">Remote</span>}
          <ExperienceBadge level={job.experience_level} />
          {job.employment_type && <span className="meta-soft">{job.employment_type}</span>}
        </p>
        <p className="job-foot">
          <span>{posted ? `Posted ${posted.toLowerCase()}` : "Posting date not listed"}</span>
          {job.similar_count > 1 && <span>· {job.similar_count} postings for this opening</span>}
        </p>
      </div>
      <div className="job-actions">
        <ApplyButton job={job} />
        <div className="job-actions-row">
          <SaveButton job={job} compact />
          <ShareButton job={job} compact />
        </div>
      </div>
    </li>
  );
}
