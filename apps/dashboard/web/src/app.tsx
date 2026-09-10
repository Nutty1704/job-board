import { Authenticator } from "@aws-amplify/ui-react";
import { Dashboard } from "./dashboard";

export function DashboardApp() {
  return (
    <Authenticator hideSignUp>
      <Dashboard />
    </Authenticator>
  );
}
