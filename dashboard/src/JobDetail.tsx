// The body of a job: used by the side panel on the jobs list and by the full /job/:id page.
import { useMemo } from "react";
import DOMPurify from "dompurify";
import { JobDetail as Job } from "./api";
import { ApplyButton, SaveButton, ShareButton } from "./actions";
import { CATEGORY_NAMES, place, relativeDate } from "./format";
import { ExperienceBadge } from "./JobCard";
import { myJobs, STATUS_LABELS, TrackStatus, useTrackedJob } from "./store";

// Links inside descriptions open in a new tab without giving the other site access to this page.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

// Job descriptions come from third-party sites: strip scripts, inline styles and anything interactive.
function sanitize(html: string): string {
  const looksLikeHtml = /<[a-z][\s\S]*>/i.test(html);
  const source = looksLikeHtml ? html : html.split(/\n{2,}/).map((p) => `<p>${p.replace(/</g, "&lt;")}</p>`).join("");
  return DOMPurify.sanitize(source, {
    FORBID_TAGS: ["style", "form", "input", "button", "iframe", "img", "video", "audio"],
    FORBID_ATTR: ["style", "class", "id"],
  });
}

function TrackerRow({ job }: { job: Job }) {
  const tracked = useTrackedJob(job.id);
  return (
    <label className="tracker-row">
      <span>My status</span>
      <select value={tracked?.status || ""}
        onChange={(e) => (e.target.value ? myJobs.setStatus(job, e.target.value as TrackStatus) : myJobs.remove(job.id))}>
        <option value="">Not tracking</option>
        {(Object.keys(STATUS_LABELS) as TrackStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
      </select>
    </label>
  );
}

export default function JobDetailBody({ job, onOpenSimilar, headingLevel = 2 }: {
  job: Job; onOpenSimilar?: (id: number) => void; headingLevel?: 1 | 2;
}) {
  const description = useMemo(() => (job.description ? sanitize(job.description) : null), [job]);
  const posted = relativeDate(job.posted_at);
  const Title = headingLevel === 1 ? "h1" : "h2";

  return (
    <>
      <p className="detail-company">{job.company}</p>
      <Title className="detail-title">{job.title}</Title>
      <p className="job-meta">
        <span>{place(job)}</span>
        {job.is_remote && <span className="badge remote">Remote</span>}
        <ExperienceBadge level={job.experience_level} />
      </p>
      {!job.active && (
        <div className="notice error">This opening has closed on {job.company}'s careers site. Look for similar jobs below.</div>
      )}
      <dl className="facts">
        {job.category && (<><dt>Category</dt><dd>{CATEGORY_NAMES[job.category] || job.category}</dd></>)}
        {job.experience_years !== null && (<><dt>Experience asked</dt><dd>{job.experience_years}+ years</dd></>)}
        {job.employment_type && (<><dt>Type</dt><dd>{job.employment_type}</dd></>)}
        {job.department && (<><dt>Team</dt><dd>{job.department}</dd></>)}
        <dt>Posted</dt><dd>{posted || "Not listed"}</dd>
        {job.location && job.location !== place(job) && (<><dt>All locations</dt><dd>{job.location}</dd></>)}
      </dl>
      {job.active && <ApplyButton job={job} wide label={`Apply on ${job.company}'s careers site`} />}
      <div className="detail-actions">
        <SaveButton job={job} />
        <ShareButton job={job} />
      </div>
      <TrackerRow job={job} />
      {job.similar_postings.length > 0 && (
        <div className="similar">
          <h3>Also posted as</h3>
          <ul>
            {job.similar_postings.map((s) => (
              <li key={s.id}>
                {onOpenSimilar
                  ? <button className="link-button" onClick={() => onOpenSimilar(s.id)}>{s.location || "Another posting"}</button>
                  : <a href={`/job/${s.id}`}>{s.location || "Another posting"}</a>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <h3>Job description</h3>
      {description ? (
        <div className="description" dangerouslySetInnerHTML={{ __html: description }} />
      ) : (
        <p className="muted">Read the full job description on {job.company}'s careers site using the Apply button above.</p>
      )}
      <p className="muted small">
        Experience level and category are worked out automatically from the posting and can be wrong; check the
        requirements on the careers site before applying. FirstOffer never asks for money to apply.
      </p>
    </>
  );
}
