// React Grab — hover an element, ⌘C, and the paste carries its source location
// for an agent. Dev only, and the gate is what makes that true: Vite replaces
// `import.meta.env.DEV` with a literal `false` in a build, so the dynamic
// import is dead code the bundler drops entirely rather than a runtime check
// shipping a 386kB overlay to production.
//
// Dynamic, and above the imports, because that is what the package documents
// for Vite. Static imports hoist above this block regardless, so it is the
// reading order that changes, not the execution order.
if (import.meta.env.DEV) {
  import("react-grab");
}

import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

createRoot(document.getElementById("root")!).render(<App />);
