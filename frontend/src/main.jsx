import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import DiamondCode from "./DiamondCode.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <DiamondCode />
  </StrictMode>
);
