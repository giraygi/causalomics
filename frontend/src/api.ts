import type { Analysis, Dataset, EdgeList, GeneResult, Network } from "./types";

const TOKEN_KEY = "causalomics_token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable (private mode etc.): token lives only for this page load
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

async function rawRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
    onUnauthorized();
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // body was not JSON
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await rawRequest(path, init);
  return (await res.json()) as T;
}

function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  async login(username: string, password: string): Promise<void> {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username, password }),
    });
    if (!res.ok) {
      throw new ApiError(
        res.status,
        res.status === 401 ? "Incorrect username or password" : `Login failed (${res.status})`,
      );
    }
    const data = (await res.json()) as { access_token: string };
    setToken(data.access_token);
  },

  logout(): void {
    setToken(null);
  },

  listDatasets: () => request<Dataset[]>("/datasets"),

  uploadDataset(expression: File, annotation: File, name?: string): Promise<Dataset> {
    const form = new FormData();
    form.append("expression", expression);
    form.append("annotation", annotation);
    if (name) form.append("name", name);
    return request<Dataset>("/datasets", { method: "POST", body: form });
  },

  listAnalyses: (datasetId: string) =>
    request<Analysis[]>(`/analyses?dataset_id=${encodeURIComponent(datasetId)}`),

  startAnalysis: (body: {
    dataset_id: string;
    reference_group: string | null;
    log_transform: boolean;
  }) => request<Analysis>("/analyses", jsonBody(body)),

  getAnalysis: (id: string) => request<Analysis>(`/analyses/${id}`),

  getResults: (id: string) => request<GeneResult[]>(`/analyses/${id}/results`),

  async downloadResultsCsv(id: string): Promise<void> {
    const res = await rawRequest(`/analyses/${id}/results?format=csv`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `results_${id}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  listEdgeLists: (analysisId?: string) => {
    const query = analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : "";
    return request<EdgeList[]>(`/edges${query}`);
  },

  uploadEdges(file: File, analysisId: string, name?: string): Promise<EdgeList> {
    const form = new FormData();
    form.append("file", file);
    form.append("analysis_id", analysisId);
    if (name) form.append("name", name);
    return request<EdgeList>("/edges", { method: "POST", body: form });
  },

  getNetwork(analysisId: string, edgeListId: string, padj: number, minAbsLfc: number) {
    const params = new URLSearchParams({
      edge_list_id: edgeListId,
      padj: String(padj),
      min_abs_lfc: String(minAbsLfc),
    });
    return request<Network>(`/analyses/${analysisId}/network?${params}`);
  },
};

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
