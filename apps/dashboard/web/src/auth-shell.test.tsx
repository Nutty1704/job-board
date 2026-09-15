import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardApp } from "./app";

vi.mock("@aws-amplify/ui-react", () => ({
  Authenticator: ({ hideSignUp }: { hideSignUp?: boolean }) => (
    <section>
      <h1>Sign in</h1>
      {!hideSignUp && <button>Create account</button>}
    </section>
  ),
}));

describe("DashboardApp", () => {
  it("shows the Cognito sign-in shell without self-service sign-up", () => {
    render(<DashboardApp />);

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
  });
});
