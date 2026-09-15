import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "./dashboard";

const { fetchAuthSession } = vi.hoisted(() => ({
  fetchAuthSession: vi.fn(),
}));

vi.mock("aws-amplify/auth", () => ({ fetchAuthSession }));

const job = {
  source: "serpapi",
  sourceJobId: "job-123",
  title: "Software Engineer",
  company: "Example Co",
  location: "Sydney",
  matchScore: 94,
  processedAt: "2026-08-30T00:00:00Z",
  sourceUrl: "https://example.com/jobs/123",
  resumeAvailable: true,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function mockSession() {
  fetchAuthSession.mockResolvedValue({
    tokens: { idToken: { toString: () => "id-token" } },
  });
}

describe("Dashboard", () => {
  it("switches between Jobs and Generate resume views", async () => {
    mockSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }))),
    );

    render(<Dashboard />);

    expect(
      screen.getByRole("button", { name: "Jobs" }).getAttribute("aria-current"),
    ).toBe("page");
    fireEvent.click(screen.getByRole("button", { name: "Generate resume" }));
    expect(
      await screen.findByRole("heading", { name: "Generate a resume" }),
    ).toBeTruthy();
    expect(
      screen
        .getByRole("navigation", { name: "Main navigation" })
        .querySelector('button[aria-current="page"]')?.textContent,
    ).toBe("Generate resume");
    expect(
      screen.queryByText(
        "No qualified roles yet. New matching jobs will appear here.",
      ),
    ).toBeNull();
  });

  it("presents a recruiter-ready dashboard without the former opportunity hero", async () => {
    mockSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            items: [job, { ...job, sourceJobId: "job-456" }],
          }),
        ),
      ),
    );

    render(<Dashboard />);

    expect(
      await screen.findByRole("heading", { name: "Job search, organised." }),
    ).toBeTruthy();
    expect(screen.queryByText("Focused opportunities")).toBeNull();
    expect(
      screen
        .getByRole("tab", { name: "Qualified" })
        .getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("loads qualified jobs by default and reloads for a selected status", async () => {
    mockSession();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [job] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] })));
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);

    expect(await screen.findByText("Software Engineer")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "scored" },
    });

    await waitFor(() =>
      expect(fetch).toHaveBeenLastCalledWith(
        "/api/jobs?status=scored",
        expect.objectContaining({
          headers: { Authorization: "Bearer id-token" },
        }),
      ),
    );
  });

  it("shows job details, source link, and downloads an available resume", async () => {
    mockSession();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [job] })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...job,
            job: {
              description: "Build useful things.",
              employment_type: "Full-time",
              via: "Example Careers",
              latitude: -33.8688,
              longitude: 151.2093,
              source_created_time: "2026-08-30T01:15:30Z",
            },
            evidence: { skills: ["TypeScript"] },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ url: "https://example.com/resume.docx" }),
        ),
      );
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Software Engineer" }),
    );
    expect(await screen.findByText("Build useful things.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Apply now" })).toHaveProperty(
      "href",
      "https://example.com/jobs/123",
    );
    expect(screen.getByText("Full-time")).toBeTruthy();
    expect(screen.getByText("Example Careers")).toBeTruthy();
    expect(screen.getByText("30 aug 2026, 11:15:30 am")).toBeTruthy();
    expect(screen.queryByText("Latitude")).toBeNull();
    expect(screen.queryByText("Longitude")).toBeNull();

    expect(
      screen.getByRole("button", { name: "Download resume" }),
    ).toBeTruthy();
  });

  it("keeps the full description visible, with parsed match evidence collapsed until requested", async () => {
    mockSession();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ items: [job] })))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              ...job,
              job: {
                description:
                  "Build useful things.\n\nLead the platform roadmap.",
              },
              evidence: {
                requiredSkills: [
                  {
                    skill: "TypeScript",
                    candidate_skill: "TypeScript",
                    evidence:
                      "Five years building production TypeScript services.",
                  },
                ],
                coreSkills: [],
                preferredSkills: [],
                skillFit: 92,
                roleAlignmentScore: 88,
              },
            }),
          ),
        ),
    );

    render(<Dashboard />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Software Engineer" }),
    );

    expect(await screen.findByText("Lead the platform roadmap.")).toBeTruthy();
    const evidence = screen.getByText("Match evidence").closest("details");
    expect(evidence).toBeTruthy();
    expect(evidence?.hasAttribute("open")).toBe(false);
    fireEvent.click(evidence?.querySelector("summary")!);
    expect(evidence?.hasAttribute("open")).toBe(true);
    expect(screen.getByText("Required skills")).toBeTruthy();
    expect(
      screen.getByText("Five years building production TypeScript services."),
    ).toBeTruthy();
  });

  it("puts apply and tailored-resume actions on every job card", async () => {
    mockSession();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [job] }))),
    );

    render(<Dashboard />);

    const card = (await screen.findByText("Software Engineer")).closest(
      "article",
    );
    expect(card).toBeTruthy();
    expect(card?.querySelector('a[aria-label="Apply"]')).toHaveProperty(
      "href",
      "https://example.com/jobs/123",
    );
    expect(
      card?.querySelector('button[aria-label="Download resume"]'),
    ).toBeTruthy();
  });

  it("prefills the resume generator from a job without a generated resume", async () => {
    mockSession();
    const jobWithoutResume = { ...job, resumeAvailable: false };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [jobWithoutResume] })),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            job: { description: "Build reliable payments services." },
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);

    const card = (await screen.findByText("Software Engineer")).closest(
      "article",
    );
    expect(
      card?.querySelector('button[aria-label="Generate resume"]'),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Download resume" }),
    ).toBeNull();
    fireEvent.click(
      card!.querySelector('button[aria-label="Generate resume"]')!,
    );

    expect(
      await screen.findByDisplayValue("Build reliable payments services."),
    ).toBeTruthy();
    await waitFor(() =>
      expect(fetch).toHaveBeenLastCalledWith(
        "/api/jobs/serpapi/job-123",
        expect.objectContaining({
          headers: { Authorization: "Bearer id-token" },
        }),
      ),
    );
  });

  it("keeps the jobs view open when a manual resume cannot be initialized", async () => {
    mockSession();
    const jobWithoutResume = { ...job, resumeAvailable: false };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [jobWithoutResume] })),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ job: {} })));
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);
    const card = (await screen.findByText("Software Engineer")).closest(
      "article",
    );
    fireEvent.click(
      card!.querySelector('button[aria-label="Generate resume"]')!,
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Could not load a job description for resume generation.",
    );
    expect(
      screen.queryByRole("heading", { name: "Generate a resume" }),
    ).toBeNull();
  });

  it("reports an error when loading a manual resume description fails", async () => {
    mockSession();
    const jobWithoutResume = { ...job, resumeAvailable: false };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [jobWithoutResume] })),
      )
      .mockResolvedValueOnce(new Response("", { status: 500 }));
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);
    const card = (await screen.findByText("Software Engineer")).closest(
      "article",
    );
    fireEvent.click(
      card!.querySelector('button[aria-label="Generate resume"]')!,
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Could not load a job description for resume generation.",
    );
    expect(
      screen.queryByRole("heading", { name: "Generate a resume" }),
    ).toBeNull();
  });

  it("offers retry after an API failure and reports unavailable resumes", async () => {
    mockSession();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [job] })))
      .mockResolvedValueOnce(new Response("", { status: 404 }));
    vi.stubGlobal("fetch", fetch);

    render(<Dashboard />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Could not load jobs.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Software Engineer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Download resume" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Resume is unavailable.",
    );
  });
});
