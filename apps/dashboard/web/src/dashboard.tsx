import { useEffect, useState } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import { ResumeGenerator } from "./resume-generator";

type Job = {
  source: string;
  sourceJobId: string;
  title: string;
  company?: string;
  location?: string;
  matchScore?: number;
  processedAt?: string;
  sourceUrl?: string;
  resumeAvailable: boolean;
};
type JobDetail = Job & { job?: Record<string, unknown>; evidence?: unknown };

const statuses = [
  { value: "qualified", label: "Qualified" },
  { value: "scored", label: "Scored" },
  { value: "all", label: "All roles" },
];

async function api(path: string) {
  const session = await fetchAuthSession();
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${session.tokens?.idToken?.toString()}` },
  });
  if (!response.ok) throw new Error("Request failed");
  return response.json();
}

async function fetchJobDetail(job: Job): Promise<JobDetail> {
  return api(
    `/jobs/${encodeURIComponent(job.source)}/${encodeURIComponent(job.sourceJobId)}`,
  );
}

function formatDate(value?: string) {
  return value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
      })
    : "Recently added";
}

function scoreStyle(score?: number) {
  if (!score) return "bg-slate-100 text-slate-600";
  return score >= 80
    ? "bg-emerald-100 text-emerald-800"
    : "bg-amber-100 text-amber-800";
}

const hiddenDetailKeys = new Set(["description", "latitude", "longitude"]);
const sourceCreatedTimeKeys = new Set([
  "source_created_time",
  "source_created_at",
]);

function formatDetailValue(key: string, value: unknown) {
  if (
    sourceCreatedTimeKeys.has(key) &&
    typeof value === "string" &&
    !Number.isNaN(Date.parse(value))
  ) {
    return new Intl.DateTimeFormat("en-AU", {
      timeZone: "Australia/Sydney",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    })
      .format(new Date(value))
      .toLowerCase();
  }
  return String(value);
}

function detailFields(job?: Record<string, unknown>) {
  if (!job) return [];
  return Object.entries(job).filter(
    ([key, value]) =>
      !hiddenDetailKeys.has(key) &&
      ["string", "number", "boolean"].includes(typeof value),
  );
}

function visibleSourceData(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(visibleSourceData);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !hiddenDetailKeys.has(key))
      .map(([key, nestedValue]) => [key, visibleSourceData(nestedValue)]),
  );
}

function detailLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

type SkillEvidence = {
  skill: string;
  candidateSkill?: string;
  explanation: string;
};

type EvidenceGroup = {
  label: string;
  skills: SkillEvidence[];
};

function skillEvidence(value: unknown): SkillEvidence[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    if (typeof record.skill !== "string" || typeof record.evidence !== "string")
      return [];
    return [
      {
        skill: record.skill,
        candidateSkill:
          typeof record.candidate_skill === "string"
            ? record.candidate_skill
            : undefined,
        explanation: record.evidence,
      },
    ];
  });
}

function matchEvidence(value: unknown): {
  groups: EvidenceGroup[];
  skillFit?: number;
  roleAlignmentScore?: number;
} {
  const record =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  return {
    groups: [
      {
        label: "Required skills",
        skills: skillEvidence(record.requiredSkills),
      },
      { label: "Core skills", skills: skillEvidence(record.coreSkills) },
      {
        label: "Preferred skills",
        skills: skillEvidence(record.preferredSkills),
      },
    ].filter((group) => group.skills.length),
    skillFit: typeof record.skillFit === "number" ? record.skillFit : undefined,
    roleAlignmentScore:
      typeof record.roleAlignmentScore === "number"
        ? record.roleAlignmentScore
        : undefined,
  };
}

function MatchEvidence({ evidence }: { evidence: unknown }) {
  const parsed = matchEvidence(evidence);
  const hasEvidence =
    parsed.groups.length ||
    parsed.skillFit !== undefined ||
    parsed.roleAlignmentScore !== undefined;

  return (
    <details className="mt-6 border-t border-slate-100 pt-5">
      <summary className="cursor-pointer text-sm font-bold text-navy marker:text-coral">
        Match evidence
      </summary>
      <div className="mt-4 space-y-4">
        {hasEvidence ? (
          <>
            {(parsed.skillFit !== undefined ||
              parsed.roleAlignmentScore !== undefined) && (
              <div className="grid grid-cols-2 gap-3">
                {parsed.skillFit !== undefined && (
                  <div className="rounded-xl bg-mint px-4 py-3">
                    <p className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-navy/60">
                      Skill fit
                    </p>
                    <p className="mt-1 text-lg font-black text-navy">
                      {parsed.skillFit}%
                    </p>
                  </div>
                )}
                {parsed.roleAlignmentScore !== undefined && (
                  <div className="rounded-xl bg-slate-100 px-4 py-3">
                    <p className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-slate-500">
                      Role alignment
                    </p>
                    <p className="mt-1 text-lg font-black text-navy">
                      {parsed.roleAlignmentScore}%
                    </p>
                  </div>
                )}
              </div>
            )}
            {parsed.groups.map((group) => (
              <section key={group.label}>
                <h4 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                  {group.label}
                </h4>
                <ul className="mt-2 space-y-2">
                  {group.skills.map((item) => (
                    <li
                      key={`${group.label}:${item.skill}`}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                    >
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="font-bold text-navy">
                          {item.skill}
                        </span>
                        {item.candidateSkill && (
                          <span className="text-xs font-semibold text-emerald-700">
                            Matched to {item.candidateSkill}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm leading-5 text-slate-600">
                        {item.explanation}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </>
        ) : (
          <p className="text-sm text-slate-500">
            No match evidence was recorded for this role.
          </p>
        )}
      </div>
    </details>
  );
}

export function Dashboard() {
  const [view, setView] = useState<"jobs" | "generate">("jobs");
  const [status, setStatus] = useState("qualified");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<JobDetail>();
  const [error, setError] = useState("");
  const [initialDescription, setInitialDescription] = useState<string>();
  const load = () => {
    void api(`/jobs?status=${status}`)
      .then((response) => {
        setJobs(response.items);
        setError("");
      })
      .catch(() => setError("Could not load jobs."));
  };
  useEffect(() => {
    load();
  }, [status]);
  const detail = (job: Job) =>
    fetchJobDetail(job)
      .then(setSelected)
      .catch(() => setError("Could not load job details."));
  const downloadResume = (job: Job) =>
    api(`/jobs/${job.source}/${job.sourceJobId}/resume`)
      .then((result) => location.assign(result.url))
      .catch(() => setError("Resume is unavailable."));
  const generateResume = (job: Job) => {
    void fetchJobDetail(job)
      .then((detail) => {
        const description = detail.job?.description;
        if (typeof description !== "string" || !description.trim()) {
          throw new Error("Missing job description");
        }
        setInitialDescription(description);
        setError("");
        setView("generate");
      })
      .catch(() =>
        setError("Could not load a job description for resume generation."),
      );
  };
  const statusLabel =
    statuses.find((item) => item.value === status)?.label.toLowerCase() ??
    status;

  return (
    <main className="min-h-screen px-4 py-5 sm:px-8 lg:px-12 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-col gap-6 border-b border-slate-300 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="grid size-11 place-items-center rounded-2xl bg-navy text-lg font-black text-mint shadow-sm">
              J
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                Personal workspace
              </p>
              <h1 className="text-lg font-bold tracking-tight text-navy">
                Job search, organised.
              </h1>
            </div>
          </div>
          <nav
            aria-label="Main navigation"
            className="flex w-fit rounded-full border border-slate-300 bg-white p-0.5 shadow-sm"
          >
            <button
              type="button"
              aria-current={view === "jobs" ? "page" : undefined}
              onClick={() => setView("jobs")}
              className={`rounded-full px-3 py-1.5 text-xs font-bold ${view === "jobs" ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              Jobs
            </button>
            <button
              type="button"
              aria-current={view === "generate" ? "page" : undefined}
              onClick={() => {
                setInitialDescription(undefined);
                setView("generate");
              }}
              className={`rounded-full px-3 py-1.5 text-xs font-bold ${view === "generate" ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              Generate resume
            </button>
          </nav>
        </header>
        {view === "generate" ? (
          <ResumeGenerator
            onNavigateToJobs={() => setView("jobs")}
            initialDescription={initialDescription}
          />
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,0.82fr)_minmax(32rem,1.18fr)]">
            <section className="min-w-0">
              <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div
                  role="tablist"
                  aria-label="Job status"
                  className="flex w-fit rounded-full border border-slate-300 bg-white p-0.5 shadow-sm"
                >
                  {statuses.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      role="tab"
                      aria-selected={status === item.value}
                      onClick={() => setStatus(item.value)}
                      className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${status === item.value ? "bg-navy text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"}`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <label className="xl:hidden">
                  <span className="sr-only">Status</span>
                  <select
                    aria-label="Status"
                    value={status}
                    onChange={(event) => setStatus(event.target.value)}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm"
                  >
                    {statuses.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {error && (
                <div
                  role="alert"
                  className="mb-5 flex items-center justify-between gap-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                >
                  <span>{error}</span>
                  <button
                    type="button"
                    onClick={load}
                    className="font-bold underline underline-offset-2"
                  >
                    Retry
                  </button>
                </div>
              )}
              <div className="space-y-3">
                {jobs.map((job) => (
                  <article
                    key={`${job.source}:${job.sourceJobId}`}
                    className={`rounded-2xl border bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${selected?.sourceJobId === job.sourceJobId ? "border-navy ring-2 ring-navy/10" : "border-slate-200"}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <button
                        type="button"
                        aria-label={job.title}
                        onClick={() => detail(job)}
                        className="text-left"
                      >
                        <p className="text-base font-bold tracking-tight text-navy hover:text-coral">
                          {job.title}
                        </p>
                        <p className="mt-0.5 text-sm font-medium text-slate-600">
                          {job.company ?? "Company not listed"}
                        </p>
                      </button>
                      <span
                        className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-black ${scoreStyle(job.matchScore)}`}
                      >
                        {job.matchScore ?? "—"}% match
                      </span>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-xs font-medium text-slate-500">
                      <span className="mr-auto">
                        {job.location ?? "Location flexible"}
                      </span>
                      <span>Added {formatDate(job.processedAt)}</span>
                      {job.sourceUrl && (
                        <a
                          href={job.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          aria-label="Apply"
                          className="inline-flex items-center rounded-lg bg-coral px-3 py-1.5 font-bold text-white transition hover:bg-[#dc6544]"
                        >
                          Apply ↗
                        </a>
                      )}
                      {job.resumeAvailable ? (
                        <button
                          type="button"
                          aria-label="Download resume"
                          onClick={() => downloadResume(job)}
                          className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-navy transition hover:border-navy hover:bg-slate-50"
                        >
                          Download resume ↓
                        </button>
                      ) : (
                        <>
                          <span>Resume unavailable</span>
                          <button
                            type="button"
                            aria-label="Generate resume"
                            onClick={() => generateResume(job)}
                            className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-navy transition hover:border-navy hover:bg-slate-50"
                          >
                            Generate resume
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                ))}
                {!jobs.length && !error && (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center text-sm text-slate-500">
                    No {statusLabel} roles yet. New matching jobs will appear
                    here.
                  </div>
                )}
              </div>
            </section>
            <aside className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm xl:sticky xl:top-8">
              {selected ? (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.16em] text-coral">
                        Role brief
                      </p>
                      <h2 className="mt-2 text-2xl font-black tracking-tight text-navy">
                        {selected.title}
                      </h2>
                      <p className="mt-1 text-sm font-medium text-slate-600">
                        {selected.company} · {selected.location}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelected(undefined)}
                      className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-navy"
                      aria-label="Close details"
                    >
                      ×
                    </button>
                  </div>
                  {selected.sourceUrl && (
                    <a
                      href={selected.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="Apply now"
                      className="mt-5 flex w-full items-center justify-center rounded-xl bg-coral px-4 py-3 text-sm font-black text-white shadow-sm transition hover:bg-[#dc6544]"
                    >
                      Apply now ↗
                    </a>
                  )}
                  <dl className="mt-6 grid grid-cols-2 gap-x-4 gap-y-4 border-y border-slate-100 py-5">
                    {detailFields(selected.job).map(([key, value]) => (
                      <div key={key}>
                        <dt className="text-[0.68rem] font-bold uppercase tracking-[0.12em] text-slate-400">
                          {detailLabel(key)}
                        </dt>
                        <dd className="mt-1 text-sm font-semibold text-navy">
                          {formatDetailValue(key, value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-6">
                    <h3 className="text-sm font-bold text-navy">Description</h3>
                    {typeof selected.job?.description === "string" ? (
                      selected.job.description
                        .split(/\n\s*\n/)
                        .map((paragraph, index) => (
                          <p
                            key={index}
                            className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-700"
                          >
                            {paragraph}
                          </p>
                        ))
                    ) : (
                      <p className="mt-3 text-sm leading-6 text-slate-700">
                        No job description was supplied by the source.
                      </p>
                    )}
                  </div>
                  <MatchEvidence evidence={selected.evidence} />
                  <details className="mt-5 border-t border-slate-100 pt-5">
                    <summary className="cursor-pointer text-sm font-bold text-navy">
                      Full source job data
                    </summary>
                    <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-100 p-4 text-xs leading-5 text-slate-700">
                      {JSON.stringify(visibleSourceData(selected.job), null, 2)}
                    </pre>
                  </details>
                </>
              ) : (
                <div className="flex min-h-72 flex-col justify-end rounded-2xl bg-mint p-6">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-navy/60">
                    Job intelligence
                  </p>
                  <h2 className="mt-3 text-2xl font-black tracking-tight text-navy">
                    Open a role to see why it fits.
                  </h2>
                  <p className="mt-3 text-sm leading-6 text-navy/70">
                    Role description, match evidence, and the tailored resume
                    are kept together for a quicker review.
                  </p>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}
