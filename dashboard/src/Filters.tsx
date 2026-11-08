import { useMemo, useState } from "react";
import { FilterOptions, JobQuery, Option } from "./api";
import { formatCount } from "./format";

interface Props {
  query: JobQuery;
  options: FilterOptions | null;
  onChange: (q: JobQuery) => void;
}

const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

const POSTED = [
  { value: null, label: "Any time" },
  { value: 1, label: "Last 24 hours" },
  { value: 3, label: "Last 3 days" },
  { value: 7, label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
];

function CheckList({ items, selected, onToggle }: { items: Option[]; selected: string[]; onToggle: (v: string) => void }) {
  return (
    <ul className="check-list">
      {items.map((o) => (
        <li key={o.value}>
          <label>
            <input type="checkbox" checked={selected.includes(o.value)} onChange={() => onToggle(o.value)} />
            <span className="check-label">{o.label || o.value}</span>
            <span className="check-count">{formatCount(o.count)}</span>
          </label>
        </li>
      ))}
    </ul>
  );
}

/** A searchable list for long option sets (countries, companies); selected values stay pinned on top. */
function SearchableList({ label, items, selected, onToggle }: { label: string; items: Option[]; selected: string[]; onToggle: (v: string) => void }) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(false);
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const matches = items.filter((o) => !selected.includes(o.value) && (!needle || o.value.toLowerCase().includes(needle)));
    const pinned = selected.map((v) => items.find((o) => o.value === v) || { value: v, count: 0 });
    return [...pinned, ...(expanded || needle ? matches : matches.slice(0, 8))];
  }, [items, selected, filter, expanded]);
  const hidden = items.length - selected.length - 8;

  return (
    <>
      <input className="mini-search" type="search" placeholder={`Find a ${label.toLowerCase()}…`} value={filter}
        onChange={(e) => setFilter(e.target.value)} aria-label={`Find a ${label.toLowerCase()}`} />
      <CheckList items={shown} selected={selected} onToggle={onToggle} />
      {!filter && hidden > 0 && (
        <button className="link-button" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}

export default function Filters({ query, options, onChange }: Props) {
  if (!options) return <p className="muted">Loading filters…</p>;
  const itCategories = options.categories.filter((c) => c.is_it);
  const otherCategories = options.categories.filter((c) => !c.is_it);

  return (
    <div className="filters">
      <fieldset>
        <legend>Experience</legend>
        <CheckList items={options.experience} selected={query.experience}
          onToggle={(v) => onChange({ ...query, experience: toggle(query.experience, v) })} />
      </fieldset>

      <fieldset>
        <legend>Job type</legend>
        <label className="switch">
          <input type="checkbox" checked={query.it_only} onChange={(e) => onChange({ ...query, it_only: e.target.checked })} />
          Hide non-IT jobs
        </label>
        <CheckList items={itCategories} selected={query.category}
          onToggle={(v) => onChange({ ...query, category: toggle(query.category, v) })} />
        <details className="more-categories">
          <summary>Other categories</summary>
          <CheckList items={otherCategories} selected={query.category}
            onToggle={(v) => onChange({ ...query, category: toggle(query.category, v) })} />
        </details>
      </fieldset>

      <fieldset>
        <legend>Location</legend>
        <label className="switch">
          <input type="checkbox" checked={query.remote} onChange={(e) => onChange({ ...query, remote: e.target.checked })} />
          Remote only <span className="check-count">{formatCount(options.remote_count)}</span>
        </label>
        <SearchableList label="Country" items={options.countries} selected={query.country}
          onToggle={(v) => onChange({ ...query, country: toggle(query.country, v) })} />
      </fieldset>

      <fieldset>
        <legend>Posted</legend>
        <ul className="check-list">
          {POSTED.map((p) => (
            <li key={p.label}>
              <label>
                <input type="radio" name="posted" checked={query.posted_within_days === p.value}
                  onChange={() => onChange({ ...query, posted_within_days: p.value })} />
                <span className="check-label">{p.label}</span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      <fieldset>
        <legend>Company</legend>
        <SearchableList label="Company" items={options.companies} selected={query.company}
          onToggle={(v) => onChange({ ...query, company: toggle(query.company, v) })} />
      </fieldset>
    </div>
  );
}
