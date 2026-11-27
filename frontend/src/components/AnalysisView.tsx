import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, api, errorMessage } from "../api";
import type { Analysis, Dataset, GeneResult } from "../types";
import ResultsTable from "./ResultsTable";

interface Props {
  analysis: Analysis | null;
  onAnalysisChange: (analysis: Analysis | null) => void;
}

const POLL_MS = 1000;

export default function AnalysisView({ analysis, onAnalysisChange }: Props) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetReload, setDatasetReload] = useState(0);
  const [datasetId, setDatasetId] = useState<string>("");
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [referenceGroup, setReferenceGroup] = useState<string>("");
  const [logTransform, setLogTransform] = useState(true);
  const [results, setResults] = useState<GeneResult[] | null>(null);

  const [expressionFile, setExpressionFile] = useState<File | null>(null);
  const [annotationFile, setAnnotationFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dataset = datasets.find((d) => d.id === datasetId) ?? null;
  const groups = dataset ? Object.keys(dataset.groups).sort() : [];

  const loadDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    try {
      const list = await api.listDatasets();
      setDatasets(list);
      setDatasetsError(null);
      return list;
    } catch (err) {
      setDatasetsError(errorMessage(err));
      throw err;
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  // Retry transient startup failures so saved datasets appear when the API becomes ready.
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    async function load() {
      try {
        const list = await loadDatasets();
        if (cancelled) return;
        setDatasetId((current) =>
          current && list.some((dataset) => dataset.id === current)
            ? current
            : list[0]?.id ?? "",
        );
      } catch (err) {
        if (cancelled) return;
        if (
          err instanceof ApiError &&
          err.status < 500 &&
          err.status !== 408 &&
          err.status !== 429
        ) {
          return;
        }
        retryTimer = setTimeout(
          () => void load(),
          Math.min(1000 * 2 ** attempt++, 10000),
        );
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) clearTimeout(retryTimer);
    };
  }, [datasetReload, loadDatasets]);

  // when the dataset changes: load its analyses and show the latest finished one
  useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;
    api
      .listAnalyses(datasetId)
      .then((list) => {
        if (cancelled) return;
        setAnalyses(list);
        const latest = list.find((a) => a.status === "done") ?? list[0] ?? null;
        onAnalysisChange(latest);
      })
      .catch((err) => setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [datasetId, onAnalysisChange]);

  // default reference group = first group alphabetically
  useEffect(() => {
    if (groups.length > 0 && !groups.includes(referenceGroup)) setReferenceGroup(groups[0]);
  }, [groups, referenceGroup]);

  // poll a running analysis until it is finished
  useEffect(() => {
    if (!analysis || (analysis.status !== "queued" && analysis.status !== "running")) return;
    const timer = setTimeout(async () => {
      try {
        const updated = await api.getAnalysis(analysis.id);
        onAnalysisChange(updated);
        setAnalyses((list) => list.map((a) => (a.id === updated.id ? updated : a)));
      } catch (err) {
        setError(errorMessage(err));
      }
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [analysis, onAnalysisChange]);

  // load results once an analysis is done
  useEffect(() => {
    setResults(null);
    if (!analysis || analysis.status !== "done") return;
    let cancelled = false;
    api
      .getResults(analysis.id)
      .then((rows) => !cancelled && setResults(rows))
      .catch((err) => setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
    // depends only on id + status so polling updates do not refetch the table
  }, [analysis?.id, analysis?.status]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!expressionFile || !annotationFile) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.uploadDataset(
        expressionFile,
        annotationFile,
        datasetName || undefined,
      );
      await loadDatasets();
      setDatasetId(created.id);
      setDatasetName("");
      (event.target as HTMLFormElement).reset();
      setExpressionFile(null);
      setAnnotationFile(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!datasetId) return;
    setBusy(true);
    setError(null);
    try {
      const started = await api.startAnalysis({
        dataset_id: datasetId,
        reference_group: referenceGroup || null,
        log_transform: logTransform,
      });
      setAnalyses((list) => [started, ...list]);
      onAnalysisChange(started);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const running = analysis?.status === "queued" || analysis?.status === "running";

  return (
    <div className="grid">
      <section className="card">
        <h2>Upload data</h2>
        <form onSubmit={upload} className="stack">
          <label>
            Expression table (CSV, genes × samples)
            <input
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={(e) => setExpressionFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
          <label>
            Sample annotation (CSV: sample, group)
            <input
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={(e) => setAnnotationFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
          <label>
            Name (optional)
            <input value={datasetName} onChange={(e) => setDatasetName(e.target.value)} />
          </label>
          <button className="primary" type="submit" disabled={busy}>
            Upload
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Run analysis</h2>
        <div className="stack">
          <label>
            Dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              {datasets.length === 0 && (
                <option value="">
                  {datasetsLoading
                    ? "Loading saved datasets…"
                    : datasetsError
                      ? "Could not load datasets"
                      : "No datasets yet"}
                </option>
              )}
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.n_genes} genes · {d.n_samples} samples
                </option>
              ))}
            </select>
          </label>
          {datasetsError && (
            <p className="error" role="alert">
              Could not load saved datasets: {datasetsError}{" "}
              <button
                type="button"
                onClick={() => setDatasetReload((reload) => reload + 1)}
                disabled={datasetsLoading}
              >
                Retry
              </button>
            </p>
          )}
          {dataset && (
            <>
              <label>
                Reference group (log2FC = other − reference)
                <select value={referenceGroup} onChange={(e) => setReferenceGroup(e.target.value)}>
                  {groups.map((g) => (
                    <option key={g} value={g}>
                      {g} (n={dataset.groups[g]})
                    </option>
                  ))}
                </select>
              </label>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={logTransform}
                  onChange={(e) => setLogTransform(e.target.checked)}
                />
                Apply log2(x+1) — untick if values are already log-scale
              </label>
              <button className="primary" onClick={run} disabled={busy || running}>
                {running ? "Running…" : "Start analysis"}
              </button>
            </>
          )}
          {analyses.length > 0 && (
            <label>
              Previous analyses
              <select
                value={analysis?.id ?? ""}
                onChange={(e) =>
                  onAnalysisChange(analyses.find((a) => a.id === e.target.value) ?? null)
                }
              >
                {analyses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {new Date(a.created_at).toLocaleString()} · {a.status}
                    {a.reference_group ? ` · ref ${a.reference_group}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p className="muted small">
            Welch's t-test per gene, Benjamini–Hochberg FDR correction.
          </p>
        </div>
      </section>

      {error && <p className="error wide">{error}</p>}
      {analysis?.status === "failed" && (
        <p className="error wide">Analysis failed: {analysis.error}</p>
      )}

      <section className="card wide">
        <div className="row between">
          <h2>Results</h2>
          {results && analysis && (
            <button onClick={() => api.downloadResultsCsv(analysis.id)}>Download CSV</button>
          )}
        </div>
        {analysis?.status === "done" && (
          <p className="muted">
            {analysis.comparison_group} vs. {analysis.reference_group} (reference)
          </p>
        )}
        {running && <p className="muted">Analysis is running…</p>}
        {!analysis && <p className="muted">Upload data and start an analysis.</p>}
        {results && <ResultsTable rows={results} />}
      </section>
    </div>
  );
}
