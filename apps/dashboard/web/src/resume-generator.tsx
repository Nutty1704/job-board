import { useEffect, useRef, useState } from "react";
import { fetchAuthSession } from "aws-amplify/auth";

export type ResumeGeneration = {
  id: string;
  status: "pending" | "completed";
  url?: string;
  error?: string;
};

export type ResumeGeneratorProps = {
  onNavigateToJobs: () => void;
  initialDescription?: string;
};

const STORAGE_KEY = "job-board:resume-generation-ids";
const MAX_SAVED_IDS = 10;
const POLL_INTERVAL_MS = 30_000;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

async function authToken() {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString();
}

async function responseError(response: Response) {
  try {
    const body = (await response.json()) as { message?: string };
    if (body.message) return body.message;
  } catch {
    // Use the generic error below when the response is not JSON.
  }
  return "Request failed.";
}

export async function submitResumeGeneration(
  description: string,
): Promise<string> {
  const token = await authToken();
  const response = await fetch("/api/resume-generations", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ description }),
  });
  if (!response.ok) throw new Error(await responseError(response));
  const body = (await response.json()) as { id?: string };
  if (!body.id) throw new Error("The API did not return a generation ID.");
  return body.id;
}

export async function fetchResumeGeneration(
  id: string,
): Promise<ResumeGeneration> {
  const token = await authToken();
  const response = await fetch(
    `/api/resume-generations/${encodeURIComponent(id)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!response.ok && response.status !== 202)
    throw new Error(await responseError(response));
  const body = (await response.json()) as {
    id?: string;
    status?: "pending" | "completed";
    url?: string;
    message?: string;
  };
  if (response.status === 202 || body.status === "pending")
    return { id: body.id ?? id, status: "pending" };
  if (response.status === 200 && body.status === "completed")
    return { id: body.id ?? id, status: "completed", url: body.url };
  throw new Error(body.message ?? "Unexpected generation status.");
}

function readSavedIds() {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "[]",
    );
    if (!Array.isArray(value)) return [];
    const ids = [
      ...new Set(value.filter((id): id is string => typeof id === "string")),
    ].slice(0, MAX_SAVED_IDS);
    if (
      ids.length !== value.length ||
      JSON.stringify(ids) !== JSON.stringify(value)
    )
      saveIds(ids);
    return ids;
  } catch {
    return [];
  }
}

function saveIds(ids: string[]) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([...new Set(ids)].slice(0, MAX_SAVED_IDS)),
  );
}

export function ResumeGenerator({
  onNavigateToJobs,
  initialDescription = "",
}: ResumeGeneratorProps) {
  const [description, setDescription] = useState(initialDescription);
  const [generations, setGenerations] = useState<ResumeGeneration[]>(() =>
    readSavedIds().map((id) => ({ id, status: "pending" })),
  );
  const [retrieveId, setRetrieveId] = useState("");
  const [error, setError] = useState("");
  const [retrieveError, setRetrieveError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const pendingIds = useRef(new Set(generations.map(({ id }) => id)));
  const idsRef = useRef(generations.map(({ id }) => id));

  const updateGeneration = (generation: ResumeGeneration) => {
    if (generation.status === "completed")
      pendingIds.current.delete(generation.id);
    setGenerations((current) =>
      current.map((item) => (item.id === generation.id ? generation : item)),
    );
  };

  const checkGeneration = async (id: string) => {
    try {
      updateGeneration(await fetchResumeGeneration(id));
    } catch (cause) {
      updateGeneration({
        id,
        status: "pending",
        error: cause instanceof Error ? cause.message : "Request failed.",
      });
    }
  };

  useEffect(() => {
    idsRef.current = generations.map(({ id }) => id);
  }, [generations]);

  useEffect(() => {
    const initialIds = [...idsRef.current];
    initialIds.forEach((id) => void checkGeneration(id));
    const interval = window.setInterval(() => {
      [...pendingIds.current].forEach((id) => void checkGeneration(id));
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  const addId = (id: string) => {
    const nextIds = [
      id,
      ...idsRef.current.filter((savedId) => savedId !== id),
    ].slice(0, MAX_SAVED_IDS);
    idsRef.current = nextIds;
    saveIds(nextIds);
    pendingIds.current = new Set(
      [...pendingIds.current].filter((pendingId) =>
        nextIds.includes(pendingId),
      ),
    );
    pendingIds.current.add(id);
    const pending: ResumeGeneration = { id, status: "pending" };
    setGenerations((current) =>
      [pending, ...current.filter((item) => item.id !== id)].slice(
        0,
        MAX_SAVED_IDS,
      ),
    );
  };

  const removeId = (id: string) => {
    const nextIds = idsRef.current.filter((savedId) => savedId !== id);
    idsRef.current = nextIds;
    pendingIds.current.delete(id);
    saveIds(nextIds);
    setGenerations((current) => current.filter((item) => item.id !== id));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!description.trim()) {
      setError("Paste a job description first.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const id = await submitResumeGeneration(description.trim());
      addId(id);
      setDescription("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not generate a resume.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const retrieve = async (event: React.FormEvent) => {
    event.preventDefault();
    const id = retrieveId.trim();
    setRetrieveError("");
    if (!UUID_PATTERN.test(id)) {
      setRetrieveError("Enter a valid UUID.");
      return;
    }
    addId(id);
    await checkGeneration(id);
  };

  return (
    <main className="min-h-screen px-4 py-5 sm:px-8 lg:px-12 lg:py-8">
      <div className="mx-auto max-w-4xl">
        <button
          type="button"
          onClick={onNavigateToJobs}
          className="mb-6 text-sm font-bold text-navy underline"
        >
          ← Jobs
        </button>
        <h2 className="text-3xl font-black tracking-tight text-navy">
          Generate a resume
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Paste a job description and we’ll tailor a resume for it.
        </p>
        <form
          onSubmit={submit}
          className="mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label
            htmlFor="job-description"
            className="text-sm font-bold text-navy"
          >
            Job description
          </label>
          <textarea
            id="job-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={9}
            className="mt-2 w-full rounded-xl border border-slate-300 p-3 text-sm"
            placeholder="Paste the full job description here"
          />
          {error && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="mt-4 rounded-xl bg-coral px-4 py-2.5 text-sm font-black text-white disabled:opacity-50"
          >
            {submitting ? "Generating…" : "Generate resume"}
          </button>
        </form>
        <form
          onSubmit={retrieve}
          className="mt-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-end"
        >
          <div className="min-w-0 flex-1">
            <label
              htmlFor="retrieve-id"
              className="text-sm font-bold text-navy"
            >
              Retrieve a resume
            </label>
            <input
              id="retrieve-id"
              aria-label="Resume generation ID"
              value={retrieveId}
              onChange={(event) => setRetrieveId(event.target.value)}
              className="mt-2 w-full rounded-xl border border-slate-300 p-2.5 font-mono text-sm"
              placeholder="Generation UUID"
            />
          </div>
          <button
            type="submit"
            className="rounded-xl border border-navy px-4 py-2.5 text-sm font-black text-navy"
          >
            Retrieve a resume
          </button>
          {retrieveError && (
            <p role="alert" className="text-sm text-red-700 sm:absolute">
              {retrieveError}
            </p>
          )}
        </form>
        <section
          className="mt-8 space-y-3"
          aria-label="Saved resume generations"
        >
          {generations.map((generation) => (
            <article
              key={generation.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <input
                  data-testid="generation-id"
                  value={generation.id}
                  readOnly
                  className="min-w-0 flex-1 bg-transparent font-mono text-xs text-slate-600"
                />
                <button
                  type="button"
                  onClick={() => removeId(generation.id)}
                  className="text-xs font-bold text-slate-500 underline"
                >
                  Remove
                </button>
              </div>
              {generation.error ? (
                <p role="alert" className="mt-3 text-sm text-red-700">
                  {generation.error}
                </p>
              ) : generation.status === "completed" && generation.url ? (
                <a
                  href={generation.url}
                  className="mt-3 inline-block text-sm font-black text-coral underline"
                >
                  Download resume
                </a>
              ) : generation.status === "completed" ? (
                <p className="mt-3 text-sm text-slate-600">
                  It may still be processing, or it may have expired after 21
                  days.
                </p>
              ) : (
                <p className="mt-3 text-sm text-slate-600">
                  Resume is still being generated. This page checks again every
                  30 seconds.
                </p>
              )}
            </article>
          ))}
          {!generations.length && (
            <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No generated resumes saved in this browser yet.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
