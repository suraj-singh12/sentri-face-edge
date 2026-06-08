import { createRoot } from "react-dom/client";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import SentriFaceApp from "./SentriFaceApp.jsx";
import "./sentriface-interface.css";

createRoot(document.getElementById("root")).render(<SentriFaceApp />);
