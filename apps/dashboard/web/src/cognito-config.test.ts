import { describe, expect, it } from "vitest";
import { createCognitoConfig } from "./cognito-config";

describe("createCognitoConfig", () => {
  it("builds Amplify Cognito settings from Vite environment values", () => {
    expect(
      createCognitoConfig({
        VITE_AWS_REGION: "ap-southeast-2",
        VITE_COGNITO_USER_POOL_ID: "ap-southeast-2_example",
        VITE_COGNITO_USER_POOL_CLIENT_ID: "dashboard-client",
      }),
    ).toEqual({
      Auth: {
        Cognito: {
          userPoolId: "ap-southeast-2_example",
          userPoolClientId: "dashboard-client",
        },
      },
    });
  });
});
