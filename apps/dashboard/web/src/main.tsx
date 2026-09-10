import "@aws-amplify/ui-react/styles.css";
import "./index.css";
import { Amplify } from "aws-amplify";
import { createRoot } from "react-dom/client";
import { DashboardApp } from "./app";
import { cognitoConfig } from "./cognito-config";

Amplify.configure(cognitoConfig);

createRoot(document.getElementById("root")!).render(<DashboardApp />);
