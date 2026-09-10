import assert from "node:assert/strict";
import test from "node:test";
import {
  enqueueManualResume,
  getManualResume,
  validateGenerationId,
} from "../src/resume-generations.js";

const id = "123e4567-e89b-12d3-a456-426614174000";

test("enqueues a manual resume using the current matching profile version", async () => {
  const sent: Record<string, unknown>[] = [];
  const result = await enqueueManualResume(
    { description: "Build reliable APIs with TypeScript." },
    {
      profile: async () => ({ body: "profile", version: "profile-v9" }),
      send: async (message) => {
        sent.push(message);
      },
      createId: () => id,
    },
  );

  assert.deepEqual(result, { id });
  assert.deepEqual(sent, [
    {
      QueueUrl: undefined,
      MessageBody: JSON.stringify({
        source: "manual",
        source_job_id: id,
        profile_s3_version: "profile-v9",
        job_event: {
          job: {
            title: "Pasted job description",
            description: "Build reliable APIs with TypeScript.",
          },
        },
      }),
    },
  ]);
});

test("rejects blank, non-string, and oversized descriptions", async () => {
  for (const body of [
    {},
    { description: "   " },
    { description: 42 },
    { description: "x".repeat(50_001) },
  ]) {
    await assert.rejects(
      () =>
        enqueueManualResume(body, {
          profile: async () => ({ body: "profile", version: "profile-v9" }),
          send: async () => undefined,
        }),
      /description/,
    );
  }
});

test("reports pending when the manual artifact is not available", async () => {
  const result = await getManualResume(id, {
    head: async () => {
      throw Object.assign(new Error("missing"), { name: "NotFound" });
    },
    sign: async () => "unused",
  });
  assert.deepEqual(result, { id, status: "pending" });
});

test("returns a five-minute signed URL for an available manual artifact", async () => {
  let signInput: Record<string, unknown> | undefined;
  const result = await getManualResume(id, {
    head: async () => undefined,
    sign: async (input) => {
      signInput = input;
      return "https://download.example/resume";
    },
  });
  assert.deepEqual(result, {
    id,
    status: "completed",
    url: "https://download.example/resume",
  });
  assert.deepEqual(signInput, { id, expiresIn: 300 });
});

test("rejects malformed generation IDs", () => {
  assert.throws(() => validateGenerationId("not-a-uuid"), /UUID/);
});
