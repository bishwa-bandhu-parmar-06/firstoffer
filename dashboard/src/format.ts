const DAY = 24 * 60 * 60 * 1000;

/** "Today", "Yesterday", "5 days ago", "3 weeks ago", or a date for older posts. */
export function relativeDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const days = Math.floor((Date.now() - date.getTime()) / DAY);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.floor(days / 7)} weeks ago`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function place(job: { city: string | null; country: string | null; location: string | null }): string {
  if (job.city && job.country) return `${job.city}, ${job.country}`;
  return job.city || job.country || job.location || "Location not listed";
}

export const formatCount = (n: number) => n.toLocaleString();

/** First seen in the last 24 hours. */
export function isNew(firstSeen: string | null): boolean {
  if (!firstSeen) return false;
  const t = new Date(firstSeen).getTime();
  return Number.isFinite(t) && Date.now() - t < DAY;
}

export const CATEGORY_NAMES: Record<string, string> = {
  software: "Software Development", data_ai: "Data & AI", devops_cloud: "Cloud & DevOps", security: "Cybersecurity",
  qa_testing: "QA & Testing", hardware_embedded: "Hardware & Embedded", networking: "Networking & Telecom",
  it_support: "IT Support & Operations", consulting_tech: "Tech Consulting & Enterprise Apps",
  product_design: "Product & Design", non_it: "Non-IT", other: "Unclassified",
};

export const EXPERIENCE_SHORT: Record<string, string> = {
  intern: "Internship",
  fresher: "Fresher",
  junior: "Junior",
  mid: "Mid level",
  senior: "Senior",
  leadership: "Leadership",
};

/** Levels a fresher can realistically apply to; mirrors FRESHER_FRIENDLY in app/classify.py. */
export const FRESHER_LEVELS = ["intern", "fresher", "junior"];
