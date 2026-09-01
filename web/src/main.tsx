/** Entry point. Nothing but mounting: every decision lives in `App`. */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";

const container = document.getElementById("root");
if (container === null) throw new Error("index.html is missing its #root element");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
