import { randomUUID } from "node:crypto";

export const MANUAL_RESUME_TITLE = "Pasted job description";
export const MAX_DESCRIPTION_LENGTH = 50_000;

type ManualRequest = { description?: unknown };
type EnqueueDependencies = {
  profile: () => Promise<{ body: string; version: string }>;
  send: (message: {
    QueueUrl: string | undefined;
    MessageBody: string;
  }) => Promise<void>;
  createId?: () => string;
};

export function validateGenerationId(value: string) {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  ) {
    throw new Error("Generation ID must be a UUID");
  }
  return value;
}

export async function enqueueManualResume(
  body: ManualRequest,
  dependencies: EnqueueDependencies,
) {
  if (typeof body?.description !== "string" || !body.description.trim()) {
    throw new Error("description must be a non-empty string");
  }
  if (body.description.length > MAX_DESCRIPTION_LENGTH) {
    throw new Error(
      `description must be at most ${MAX_DESCRIPTION_LENGTH} characters`,
    );
  }
  const id = dependencies.createId?.() ?? randomUUID();
  const profile = await dependencies.profile();
  await dependencies.send({
    QueueUrl: process.env.HIGH_MATCH_JOBS_QUEUE_URL,
    MessageBody: JSON.stringify({
      source: "manual",
      source_job_id: id,
      profile_s3_version: profile.version,
      job_event: {
        job: { title: MANUAL_RESUME_TITLE, description: body.description },
      },
    }),
  });
  return { id };
}

type StatusDependencies = {
  head: () => Promise<void>;
  sign: (input: { id: string; expiresIn: number }) => Promise<string>;
};

export async function getManualResume(
  id: string,
  dependencies: StatusDependencies,
) {
  validateGenerationId(id);
  try {
    await dependencies.head();
  } catch (error: any) {
    if (
      error?.name === "NotFound" ||
      error?.name === "NoSuchKey" ||
      error?.$metadata?.httpStatusCode === 404
    ) {
      return { id, status: "pending" as const };
    }
    throw error;
  }
  return {
    id,
    status: "completed" as const,
    url: await dependencies.sign({ id, expiresIn: 300 }),
  };
}
