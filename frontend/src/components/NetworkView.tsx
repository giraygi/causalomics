import { useEffect, useRef, useState, type FormEvent } from "react";
import cytoscape from "cytoscape";
import { api, errorMessage } from "../api";
import { divergingColor } from "../color";
import type { Analysis, EdgeList, Network, NetworkNode } from "../types";

interface Props {
  analysis: Analysis | null;
  visible: boolean;
}

export default function NetworkView({ analysis, visible }: Props) {
  const [edgeLists, setEdgeLists] = useState<EdgeList[]>([]);
  const [edgeListId, setEdgeListId] = useState("");
  const [edgeFile, setEdgeFile] = useState<File | null>(null);
  const [edgeListName, setEdgeListName] = useState("");
  const [padj, setPadj] = useState(0.05);
  const [minAbsLfc, setMinAbsLfc] = useState(1);
  const [network, setNetwork] = useState<Network | null>(null);
  const [selected, setSelected] = useState<NetworkNode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  async function loadEdgeLists(analysisId: string) {
    try {
      const list = await api.listEdgeLists(analysisId);
      setEdgeLists(list);
      setEdgeListId(list[0]?.id || "");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    if (visible && analysis?.status === "done") {
      setEdgeListId("");
      let cancelled = false;
      api
        .listEdgeLists(analysis.id)
        .then((list) => {
          if (cancelled) return;
          setEdgeLists(list);
          setEdgeListId(list[0]?.id || "");
        })
        .catch((err) => {
          if (!cancelled) setError(errorMessage(err));
        });
      return () => {
        cancelled = true;
      };
    } else {
      setEdgeLists([]);
      setEdgeListId("");
    }
  }, [visible, analysis?.id, analysis?.status]);

  // a different analysis invalidates the drawn network
  useEffect(() => {
    setNetwork(null);
    setSelected(null);
    setEdgeFile(null);
    setEdgeListName("");
  }, [analysis?.id]);

  async function uploadEdges(event: FormEvent) {
    event.preventDefault();
    if (!edgeFile || analysis?.status !== "done") return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.uploadEdges(
        edgeFile,
        analysis.id,
        edgeListName.trim() || undefined,
      );
      await loadEdgeLists(analysis.id);
      setEdgeListId(created.id);
      (event.target as HTMLFormElement).reset();
      setEdgeFile(null);
      setEdgeListName("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function show() {
    if (!analysis || !edgeListId) return;
    setBusy(true);
    setError(null);
    setSelected(null);
    try {
      setNetwork(await api.getNetwork(analysis.id, edgeListId, padj, minAbsLfc));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // (re)draw the graph whenever new network data arrives
  useEffect(() => {
    cyRef.current?.destroy();
    cyRef.current = null;
    if (!network || !containerRef.current || network.nodes.length === 0) return;

    const maxAbs = Math.max(network.max_abs_log2_fold_change, 1e-9);
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...network.nodes.map((n) => ({
          data: { id: n.id, lfc: n.log2_fold_change, color: divergingColor(n.log2_fold_change, maxAbs) },
        })),
        ...network.edges.map((e, i) => ({
          data: { id: `e${i}`, source: e.source, target: e.target, score: e.score ?? 0.5 },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "border-width": 1,
            "border-color": "#555",
            label: "data(id)",
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 3,
            width: 22,
            height: 22,
          },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(score, 0, 1, 0.5, 4)",
            "line-color": "#b8b8b8",
            "curve-style": "haystack",
          },
        },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#111" } },
      ],
      layout: { name: "cose", animate: false, padding: 30, nodeRepulsion: () => 8000 },
      wheelSensitivity: 0.3,
    });
    cy.on("tap", "node", (evt) => {
      const id = evt.target.id();
      setSelected(network.nodes.find((n) => n.id === id) ?? null);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelected(null);
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [network]);

  // Cytoscape cannot measure a hidden container; refit when the tab becomes visible.
  useEffect(() => {
    if (visible && cyRef.current) {
      cyRef.current.resize();
      cyRef.current.fit(undefined, 30);
    }
  }, [visible]);

  const maxAbs = network?.max_abs_log2_fold_change ?? 0;

  return (
    <div className="grid">
      {analysis?.status === "done" ? (
        <section className="card">
          <h2>Interaction list for this analysis</h2>
          <form key={analysis.id} onSubmit={uploadEdges} className="stack">
            <label>
              Upload edge list (CSV: gene_a, gene_b[, score] — STRING exports also work)
              <input
                type="file"
                accept=".csv,.tsv,.txt"
                onChange={(e) => setEdgeFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <label>
              Name for this analysis (optional)
              <input value={edgeListName} onChange={(e) => setEdgeListName(e.target.value)} />
            </label>
            <button type="submit" disabled={busy}>
              Upload
            </button>
          </form>
          <label>
            Interaction list
            <select value={edgeListId} onChange={(e) => setEdgeListId(e.target.value)}>
              {edgeLists.length === 0 && <option value="">No interaction lists yet</option>}
              {edgeLists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} · {l.n_edges} interactions
                </option>
              ))}
            </select>
          </label>
          {edgeLists.length === 0 && (
            <p className="muted small">
              Interaction lists belong to an analysis. Select the analysis that owns a saved list
              in the Analysis tab, or upload a new one here.
            </p>
          )}
        </section>
      ) : (
        <section className="card">
          <h2>Interaction list</h2>
          <p className="muted">
            Select a finished analysis in the Analysis tab to upload and name its interaction
            list.
          </p>
        </section>
      )}

      {error && <p className="error wide">{error}</p>}

      {analysis?.status === "done" ? (
        <>
          <section className="card">
            <h2>Filter</h2>
            <div className="stack">
              <label>
                adj. p below
                <input
                  type="number"
                  min={0.0001}
                  max={1}
                  step={0.01}
                  value={padj}
                  onChange={(e) => setPadj(Number(e.target.value) || 0.05)}
                />
              </label>
              <label>
                |log2 FC| at least
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={minAbsLfc}
                  onChange={(e) => setMinAbsLfc(Math.max(Number(e.target.value) || 0, 0))}
                />
              </label>
              <button className="primary" onClick={show} disabled={busy || !edgeListId}>
                Show network
              </button>
            </div>
          </section>

          <section className="card wide">
            <div className="row between">
              <h2>Significant genes</h2>
              {network && (
                <span className="muted">
                  {network.n_significant} genes · {network.edges.length} interactions
                </span>
              )}
            </div>
            {network && network.nodes.length === 0 && (
              <p className="muted">No genes pass the current thresholds.</p>
            )}
            <div className="network-wrap">
              <div ref={containerRef} className="network" />
              {network && network.nodes.length > 0 && (
                <aside className="legend">
                  <div className="legend-title">log2 fold change</div>
                  <div
                    className="legend-bar"
                    style={{
                      background: `linear-gradient(to right, ${divergingColor(-1, 1)}, ${divergingColor(0, 1)}, ${divergingColor(1, 1)})`,
                    }}
                  />
                  <div className="row between small">
                    <span>{(-maxAbs).toFixed(1)}</span>
                    <span>0</span>
                    <span>+{maxAbs.toFixed(1)}</span>
                  </div>
                  <p className="small muted">
                    Blue: lower in {analysis.comparison_group}. Red: higher.
                  </p>
                  {selected && (
                    <div className="node-info">
                      <strong>{selected.id}</strong>
                      <div>log2 FC: {selected.log2_fold_change.toFixed(2)}</div>
                      <div>adj. p: {selected.p_adjusted?.toExponential(2) ?? "–"}</div>
                    </div>
                  )}
                </aside>
              )}
            </div>
          </section>
        </>
      ) : (
        <section className="card">
          <h2>Network</h2>
          <p className="muted">
            Upload an interaction list above. Run (or select) a finished analysis to view a
            network.
          </p>
        </section>
      )}
    </div>
  );
}
