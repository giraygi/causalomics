export interface Dataset {
  id: string;
  name: string;
  created_at: string;
  n_genes: number;
  n_samples: number;
  groups: Record<string, number>;
}

export type AnalysisStatus = "queued" | "running" | "done" | "failed";

export interface Analysis {
  id: string;
  dataset_id: string;
  status: AnalysisStatus;
  error: string | null;
  reference_group: string | null;
  comparison_group: string | null;
  log_transform: boolean;
  created_at: string;
  finished_at: string | null;
}

export interface GeneResult {
  gene: string;
  mean_reference: number;
  mean_comparison: number;
  log2_fold_change: number;
  t_statistic: number | null;
  p_value: number | null;
  p_adjusted: number | null;
}

export interface EdgeList {
  id: string;
  name: string;
  created_at: string;
  n_edges: number;
}

export interface NetworkNode {
  id: string;
  log2_fold_change: number;
  p_adjusted: number | null;
}

export interface NetworkEdge {
  source: string;
  target: string;
  score: number | null;
}

export interface Network {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  n_significant: number;
  max_abs_log2_fold_change: number;
}
