import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchResumeGeneration,
  ResumeGenerator,
  submitResumeGeneration,
} from "./resume-generator";

const { fetchAuthSession } = vi.hoisted(() => ({ fetchAuthSession: vi.fn() }));
vi.mock("aws-amplify/auth", () => ({ fetchAuthSession }));

const ids = Array.from(
  { length: 12 },
  (_, index) => `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
);

beforeEach(() => {
  fetchAuthSession.mockResolvedValue({
    tokens: { idToken: { toString: () => "id-token" } },
  });
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("resume generation API", () => {
  it("submits a description and returns the generated ID", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: ids[0] }), { status: 202 }),
      );
    vi.stubGlobal("fetch", fetch);

    await expect(
      submitResumeGeneration("Build a payments platform"),
    ).resolves.toBe(ids[0]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/resume-generations",
      expect.objectContaining({
        method: "POST",
        headers: {
          "content-type": "application/json",
          Authorization: "Bearer id-token",
        },
        body: JSON.stringify({ description: "Build a payments platform" }),
      }),
    );
  });

  it("parses pending and completed status responses", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: ids[0], status: "pending" }), {
          status: 202,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: ids[0],
            status: "completed",
            url: "https://signed.example/resume.docx",
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);

    await expect(fetchResumeGeneration(ids[0])).resolves.toEqual({
      id: ids[0],
      status: "pending",
    });
    await expect(fetchResumeGeneration(ids[0])).resolves.toEqual({
      id: ids[0],
      status: "completed",
      url: "https://signed.example/resume.docx",
    });
  });

  it("surfaces API messages and rejects blank descriptions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: "Description is too long" }), {
          status: 400,
        }),
      ),
    );
    await expect(submitResumeGeneration("description")).rejects.toThrow(
      "Description is too long",
    );

    render(<ResumeGenerator onNavigateToJobs={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Generate resume" }));
    expect(screen.getByRole("alert").textContent).toContain(
      "Paste a job description first.",
    );
  });
});

describe("ResumeGenerator", () => {
  it("submits a supplied initial description only after the user requests generation", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: ids[0] }), { status: 202 }),
      );
    vi.stubGlobal("fetch", fetch);

    render(
      <ResumeGenerator
        onNavigateToJobs={vi.fn()}
        initialDescription="Build a payments platform"
      />,
    );

    expect(screen.getByDisplayValue("Build a payments platform")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Generate resume" }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/resume-generations",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ description: "Build a payments platform" }),
        }),
      ),
    );
  });

  it("loads and caps saved IDs, then removes an ID", async () => {
    localStorage.setItem(
      "job-board:resume-generation-ids",
      JSON.stringify(ids),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ status: "pending" }), {
            status: 202,
          }),
        ),
      ),
    );

    render(<ResumeGenerator onNavigateToJobs={vi.fn()} />);
    expect(
      (await screen.findAllByTestId("generation-id")).map(
        (item) => item.textContent,
      ),
    ).toHaveLength(10);
    expect(screen.getByDisplayValue(ids[9])).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(screen.queryByDisplayValue(ids[0])).toBeNull();
  });

  it("fetches pending IDs on mount and polls them after 30 seconds, but not completed IDs", async () => {
    vi.useFakeTimers();
    localStorage.setItem(
      "job-board:resume-generation-ids",
      JSON.stringify([ids[0], ids[1]]),
    );
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: ids[0], status: "pending" }), {
          status: 202,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: ids[1],
            status: "completed",
            url: "https://signed.example/resume.docx",
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: ids[0],
            status: "completed",
            url: "https://signed.example/new.docx",
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);

    render(<ResumeGenerator onNavigateToJobs={vi.fn()} />);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    vi.advanceTimersByTime(30_000);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(fetch.mock.calls[2][0]).toBe(`/api/resume-generations/${ids[0]}`);
    expect(
      fetch.mock.calls.filter(
        ([path]) => path === `/api/resume-generations/${ids[1]}`,
      ),
    ).toHaveLength(1);
  });

  it("retrieves a UUID and displays a completed download link", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: ids[0],
          status: "completed",
          url: "https://signed.example/resume.docx",
        }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    render(<ResumeGenerator onNavigateToJobs={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Resume generation ID"), {
      target: { value: ids[0] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Retrieve a resume" }));
    expect(
      await screen.findByRole("link", { name: "Download resume" }),
    ).toHaveProperty("href", "https://signed.example/resume.docx");
    expect(
      JSON.parse(localStorage.getItem("job-board:resume-generation-ids")!),
    ).toEqual([ids[0]]);
  });
});
