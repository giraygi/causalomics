import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import type { GeneResult } from "../types";

// TanStack sorts `undefined` last; the API returns null for untestable genes.
interface Row {
  gene: string;
  log2_fold_change: number;
  mean_reference: number;
  mean_comparison: number;
  t_statistic?: number;
  p_value?: number;
  p_adjusted?: number;
}

const fixed = (v: number | undefined, digits = 2) => (v === undefined ? "–" : v.toFixed(digits));
const sci = (v: number | undefined) =>
  v === undefined ? "–" : v < 0.001 ? v.toExponential(2) : v.toFixed(4);

const col = createColumnHelper<Row>();
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const columns: ColumnDef<Row, any>[] = [
  col.accessor("gene", { header: "Gene" }),
  col.accessor("log2_fold_change", {
    header: "log2 FC",
    cell: (c) => <span className={c.getValue() > 0 ? "up" : "down"}>{fixed(c.getValue())}</span>,
  }),
  col.accessor("mean_reference", { header: "Mean (reference)", cell: (c) => fixed(c.getValue()) }),
  col.accessor("mean_comparison", { header: "Mean (other)", cell: (c) => fixed(c.getValue()) }),
  col.accessor("t_statistic", { header: "t", cell: (c) => fixed(c.getValue()) }),
  col.accessor("p_value", { header: "p-value", cell: (c) => sci(c.getValue()) }),
  col.accessor("p_adjusted", { header: "adj. p (BH)", cell: (c) => sci(c.getValue()) }),
];

export default function ResultsTable({ rows }: { rows: GeneResult[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "p_adjusted", desc: false }]);
  const [padjMax, setPadjMax] = useState(0.05);
  const [onlySignificant, setOnlySignificant] = useState(false);
  const [query, setQuery] = useState("");

  const data = useMemo<Row[]>(
    () =>
      rows
        .map((r) => ({
          gene: r.gene,
          log2_fold_change: r.log2_fold_change,
          mean_reference: r.mean_reference,
          mean_comparison: r.mean_comparison,
          t_statistic: r.t_statistic ?? undefined,
          p_value: r.p_value ?? undefined,
          p_adjusted: r.p_adjusted ?? undefined,
        }))
        .filter((r) => !query || r.gene.toLowerCase().includes(query.toLowerCase()))
        .filter((r) => !onlySignificant || (r.p_adjusted !== undefined && r.p_adjusted < padjMax)),
    [rows, query, onlySignificant, padjMax],
  );

  const nSignificant = useMemo(
    () => rows.filter((r) => r.p_adjusted !== null && r.p_adjusted < padjMax).length,
    [rows, padjMax],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    defaultColumn: { sortUndefined: "last" },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });

  return (
    <div>
      <div className="row controls">
        <label className="inline">
          Search gene
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. GENE012" />
        </label>
        <label className="inline">
          adj. p threshold
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={padjMax}
            onChange={(e) => setPadjMax(Number(e.target.value) || 0.05)}
            style={{ width: "6rem" }}
          />
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={onlySignificant}
            onChange={(e) => setOnlySignificant(e.target.checked)}
          />
          Only significant
        </label>
        <span className="muted">
          {nSignificant} of {rows.length} genes with adj. p &lt; {padjMax}
        </span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const dir = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className="sortable"
                      title="Click to sort"
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      <span className="sort">{dir === "asc" ? " ▲" : dir === "desc" ? " ▼" : ""}</span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const padj = row.original.p_adjusted;
              const significant = padj !== undefined && padj < padjMax;
              return (
                <tr key={row.id} className={significant ? "significant" : undefined}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="row pager">
        <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
          ‹ Prev
        </button>
        <span>
          Page {table.getState().pagination.pageIndex + 1} of {Math.max(table.getPageCount(), 1)}
        </span>
        <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
          Next ›
        </button>
        <select
          value={table.getState().pagination.pageSize}
          onChange={(e) => table.setPageSize(Number(e.target.value))}
        >
          {[25, 50, 100, 500].map((n) => (
            <option key={n} value={n}>
              {n} / page
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
