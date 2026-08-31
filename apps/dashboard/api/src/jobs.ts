export type RecordValue = Record<string, any>;
export type JobStore = {
  scan(): Promise<RecordValue[]>;
  hasResume(sourceJobId: string): Promise<boolean>;
};

const string = (value: unknown): string | undefined =>
  typeof value === "string" && value.trim() ? value : undefined;
const number = (value: unknown): number | undefined =>
  typeof value === "number" ? value : undefined;

export function mapRecord(record: RecordValue, resumeAvailable: boolean) {
  const job = record.job_event?.job ?? {};
  return {
    source: record.source,
    sourceJobId: record.source_job_id,
    title: string(job.title) ?? "Untitled role",
    company: string(job.company?.display_name) ?? undefined,
    location: string(job.location?.display_name) ?? undefined,
    matchScore: number(record.match_score),
    processedAt: string(record.processed_at),
    sourceUrl:
      string(record.job_event?.source_url) ??
      string(job.redirect_url) ??
      string(job.url),
    resumeAvailable,
  };
}

function status(value?: string) {
  return value === "all" || value === "scored" || value === "qualified"
    ? value
    : "qualified";
}
function pagination(query: Record<string, string | undefined>) {
  const page = Math.max(1, Number.parseInt(query.page ?? "1", 10) || 1);
  const pageSize = Math.min(
    100,
    Math.max(1, Number.parseInt(query.pageSize ?? "20", 10) || 20),
  );
  return { page, pageSize };
}

export async function listJobs(
  store: JobStore,
  query: Record<string, string | undefined>,
) {
  const selectedStatus = status(query.status);
  const { page, pageSize } = pagination(query);
  const rows = (await store.scan())
    .filter((item) =>
      selectedStatus === "all"
        ? item.status === "qualified" || item.status === "scored"
        : item.status === selectedStatus,
    )
    .sort(
      (a, b) =>
        (b.status === "qualified" ? 1 : 0) -
          (a.status === "qualified" ? 1 : 0) ||
        (b.match_score ?? -1) - (a.match_score ?? -1),
    );
  const slice = rows.slice((page - 1) * pageSize, page * pageSize);
  return {
    items: await Promise.all(
      slice.map(async (item) =>
        mapRecord(item, await store.hasResume(item.source_job_id)),
      ),
    ),
    page,
    pageSize,
    total: rows.length,
  };
}

export async function findJob(
  store: Pick<JobStore, "scan" | "hasResume">,
  source: string,
  sourceJobId: string,
) {
  const record = (await store.scan()).find(
    (item) => item.source === source && item.source_job_id === sourceJobId,
  );
  if (!record) return undefined;
  return {
    ...mapRecord(record, await store.hasResume(sourceJobId)),
    job: record.job_event?.job,
    evidence: {
      requiredSkills: record.required_skills ?? [],
      coreSkills: record.core_skills ?? [],
      preferredSkills: record.preferred_skills ?? [],
      skillFit: record.skill_fit,
      roleAlignmentScore: record.role_alignment_score,
    },
  };
}
