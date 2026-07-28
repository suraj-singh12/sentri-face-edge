import { createRoot } from "react-dom/client";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import SentriFaceApp from "./SentriFaceApp.jsx";
import { AppErrorBoundary } from "./components/AppErrorBoundary.jsx";
import "./sentriface-interface.css";

createRoot(document.getElementById("root")).render(
  <AppErrorBoundary>
    <SentriFaceApp />
  </AppErrorBoundary>,
);
