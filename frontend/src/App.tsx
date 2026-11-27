import { useEffect, useState } from "react";
import { api, getToken, setUnauthorizedHandler } from "./api";
import Login from "./components/Login";
import AnalysisView from "./components/AnalysisView";
import NetworkView from "./components/NetworkView";
import type { Analysis } from "./types";

type Tab = "analysis" | "network";

export default function App() {
  const [loggedIn, setLoggedIn] = useState<boolean>(() => getToken() !== null);
  const [tab, setTab] = useState<Tab>("analysis");
  // The analysis selected in the first view is the input for the network view.
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  useEffect(() => {
    setUnauthorizedHandler(() => setLoggedIn(false));
  }, []);

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>CausalOmics · Differential Expression</h1>
        <nav>
          <button
            className={tab === "analysis" ? "tab active" : "tab"}
            onClick={() => setTab("analysis")}
          >
            1. Analysis
          </button>
          <button
            className={tab === "network" ? "tab active" : "tab"}
            onClick={() => setTab("network")}
          >
            2. Network
          </button>
        </nav>
        <button
          className="link"
          onClick={() => {
            api.logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      <main>
        {/* Both views stay mounted so their state survives tab switches. */}
        <div hidden={tab !== "analysis"}>
          <AnalysisView analysis={analysis} onAnalysisChange={setAnalysis} />
        </div>
        <div hidden={tab !== "network"}>
          <NetworkView analysis={analysis} visible={tab === "network"} />
        </div>
      </main>
    </div>
  );
}
