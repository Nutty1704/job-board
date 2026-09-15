type ViteEnvironment = Record<string, string | undefined>;

export function createCognitoConfig(environment: ViteEnvironment) {
  return {
    Auth: {
      Cognito: {
        userPoolId: environment.VITE_COGNITO_USER_POOL_ID ?? "",
        userPoolClientId: environment.VITE_COGNITO_USER_POOL_CLIENT_ID ?? "",
      },
    },
  };
}

export const cognitoConfig = createCognitoConfig(import.meta.env);
