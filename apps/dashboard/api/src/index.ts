import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand } from "@aws-sdk/lib-dynamodb";
import {
  GetObjectCommand,
  HeadObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { SendMessageCommand, SQSClient } from "@aws-sdk/client-sqs";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import type { APIGatewayProxyEventV2 } from "aws-lambda";
import { findJob, listJobs } from "./jobs.js";
import {
  enqueueManualResume,
  getManualResume,
  validateGenerationId,
} from "./resume-generations.js";

const tableName = process.env.JOB_MATCHES_TABLE!;
const bucket = process.env.PROJECT_DATA_BUCKET!;
const db = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const s3 = new S3Client({});
const sqs = new SQSClient({});
async function scan() {
  let startKey: Record<string, unknown> | undefined;
  const records: Record<string, any>[] = [];
  do {
    const page = await db.send(
      new ScanCommand({ TableName: tableName, ExclusiveStartKey: startKey }),
    );
    records.push(...(page.Items ?? []));
    startKey = page.LastEvaluatedKey;
  } while (startKey);
  return records;
}
const key = (id: string) => `resumes/${id}.docx`;
const manualKey = (id: string) => `resumes/manual/${id}.docx`;
async function hasResume(id: string) {
  try {
    await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: key(id) }));
    return true;
  } catch (error: any) {
    if (error?.$metadata?.httpStatusCode === 404 || error?.name === "NotFound")
      return false;
    throw error;
  }
}
const json = (statusCode: number, body: unknown) => ({
  statusCode,
  headers: { "content-type": "application/json", "cache-control": "no-store" },
  body: JSON.stringify(body),
});
const requestBody = (event: APIGatewayProxyEventV2) => {
  const raw = event.isBase64Encoded
    ? Buffer.from(event.body ?? "", "base64").toString("utf8")
    : (event.body ?? "");
  return JSON.parse(raw || "{}");
};
export async function handler(event: APIGatewayProxyEventV2) {
  try {
    const segments = event.rawPath
      .split("/")
      .filter(Boolean)
      .map(decodeURIComponent);
    if (segments[0] === "api") segments.shift();
    const store = { scan, hasResume };
    if (segments[0] === "resume-generations") {
      if (
        event.requestContext.http.method === "POST" &&
        segments.length === 1
      ) {
        const result = await enqueueManualResume(requestBody(event), {
          profile: async () => {
            const response = await s3.send(
              new GetObjectCommand({
                Bucket: bucket,
                Key: "matching/current.json",
              }),
            );
            const version = response.VersionId;
            if (!version || !response.Body)
              throw new Error("Matching profile object has no version");
            const body = await response.Body.transformToString();
            return { body, version };
          },
          send: async (message) => {
            await sqs.send(new SendMessageCommand(message));
          },
        });
        return json(202, result);
      }
      if (event.requestContext.http.method === "GET" && segments.length === 2) {
        validateGenerationId(segments[1]);
        const result = await getManualResume(segments[1], {
          head: async () => {
            await s3.send(
              new HeadObjectCommand({
                Bucket: bucket,
                Key: manualKey(segments[1]),
              }),
            );
          },
          sign: async () =>
            getSignedUrl(
              s3,
              new GetObjectCommand({
                Bucket: bucket,
                Key: manualKey(segments[1]),
              }),
              { expiresIn: 300 },
            ),
        });
        return json(result.status === "pending" ? 202 : 200, result);
      }
      return json(404, { message: "Not found" });
    }
    if (event.requestContext.http.method !== "GET" || segments[0] !== "jobs")
      return json(404, { message: "Not found" });
    if (segments.length === 1)
      return json(
        200,
        await listJobs(store, event.queryStringParameters ?? {}),
      );
    if (segments.length === 3 && segments[2] !== "resume") {
      const result = await findJob(store, segments[1], segments[2]);
      return result
        ? json(200, result)
        : json(404, { message: "Job not found" });
    }
    if (segments.length === 4 && segments[3] === "resume") {
      const result = await findJob(store, segments[1], segments[2]);
      if (!result || !result.resumeAvailable)
        return json(404, { message: "Resume not found" });
      const url = await getSignedUrl(
        s3,
        new GetObjectCommand({ Bucket: bucket, Key: key(segments[2]) }),
        { expiresIn: 300 },
      );
      return json(200, { url });
    }
    return json(404, { message: "Not found" });
  } catch (error: any) {
    if (
      error instanceof SyntaxError ||
      error?.message?.includes("description") ||
      error?.message?.includes("UUID")
    ) {
      return json(400, { message: error.message });
    }
    console.error(error);
    return json(500, { message: "Unable to load jobs" });
  }
}
