import assert from "node:assert/strict";
import test from "node:test";
import { listJobs, mapRecord } from "../src/jobs.js";

const records = [
  {
    source: "adzuna",
    source_job_id: "1",
    status: "scored",
    match_score: 90,
    processed_at: "2026-01-01T00:00:00Z",
    job_event: {
      job: {
        title: "Scored",
        company: { display_name: "A" },
        location: { display_name: "Sydney" },
      },
    },
  },
  {
    source: "adzuna",
    source_job_id: "2",
    status: "qualified",
    match_score: 80,
    processed_at: "2026-01-02T00:00:00Z",
    job_event: {
      job: {
        title: "Qualified",
        redirect_url: "https://example.test/job",
        company: { display_name: "B" },
        location: { display_name: "Sydney" },
      },
    },
  },
];

test("maps normalized dashboard job summaries", () => {
  assert.deepEqual(mapRecord(records[1] as any, true), {
    source: "adzuna",
    sourceJobId: "2",
    title: "Qualified",
    company: "B",
    location: "Sydney",
    matchScore: 80,
    processedAt: "2026-01-02T00:00:00Z",
    sourceUrl: "https://example.test/job",
    resumeAvailable: true,
  });
});

test("defaults to qualified jobs, scores descending, and paginates", async () => {
  const response = await listJobs(
    { scan: async () => records as any, hasResume: async () => false },
    {},
  );
  assert.equal(response.total, 1);
  assert.equal(response.items[0].title, "Qualified");
  const all = await listJobs(
    { scan: async () => records as any, hasResume: async () => false },
    { status: "all", pageSize: "1", page: "2" },
  );
  assert.equal(all.items[0].title, "Scored");
});
