import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChatArtifact } from "../types";
import { chartPalette } from "./palette";

type Row = Record<string, unknown>;

const X_KEYS = ["x", "t", "name", "label", "date", "time", "category"];

/** Coax a chart payload into rows. Accepts a bare array, `{data:[…]}`,
 *  `{points:[…]}`, or `{series:[…]}`; anything else yields an empty set the
 *  caller renders as an empty-state rather than crashing. */
function toRows(content: string): Row[] {
  try {
    const parsed = JSON.parse(content) as unknown;
    if (Array.isArray(parsed)) return parsed as Row[];
    if (parsed && typeof parsed === "object") {
      for (const key of ["data", "points", "series", "rows"]) {
        const value = (parsed as Row)[key];
        if (Array.isArray(value)) return value as Row[];
      }
    }
  } catch {
    // fall through to empty
  }
  return [];
}

function pickXKey(rows: Row[]): string {
  const keys = rows.length ? Object.keys(rows[0]) : [];
  return keys.find((k) => X_KEYS.includes(k.toLowerCase())) ?? keys[0] ?? "x";
}

function numericKeys(rows: Row[], xKey: string): string[] {
  if (!rows.length) return [];
  return Object.keys(rows[0]).filter(
    (k) => k !== xKey && typeof rows[0][k] === "number",
  );
}

export function ChartArtifact({ artifact }: { artifact: ChatArtifact }) {
  const rows = toRows(artifact.content);
  const xKey = pickXKey(rows);
  const series = numericKeys(rows, xKey);
  const kind = artifact.type.toLowerCase();
  const palette = chartPalette();
  const colors = palette.series;

  const empty = rows.length === 0 || series.length === 0;

  return (
    <figure className="my-2 rounded border border-slate-700 bg-slate-900 p-3">
      {artifact.title ? (
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      {empty ? (
        <p className="text-xs text-slate-500">—</p>
      ) : (
        <div className="h-64 w-full" dir="ltr">
          <ResponsiveContainer width="100%" height="100%">
            {kind.includes("pie") || kind.includes("donut") ? (
              <PieChart>
                <Pie
                  data={rows as Row[]}
                  dataKey={series[0]}
                  nameKey={xKey}
                  innerRadius={kind.includes("donut") ? 50 : 0}
                  outerRadius={90}
                >
                  {rows.map((_, index) => (
                    <Cell key={index} fill={colors[index % colors.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            ) : kind.includes("bar") ? (
              <BarChart data={rows}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                <XAxis dataKey={xKey} stroke={palette.axis} fontSize={11} />
                <YAxis stroke={palette.axis} fontSize={11} />
                <Tooltip />
                {series.map((key, index) => (
                  <Bar key={key} dataKey={key} fill={colors[index % colors.length]} />
                ))}
              </BarChart>
            ) : kind.includes("area") ? (
              <AreaChart data={rows}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                <XAxis dataKey={xKey} stroke={palette.axis} fontSize={11} />
                <YAxis stroke={palette.axis} fontSize={11} />
                <Tooltip />
                {series.map((key, index) => (
                  <Area
                    key={key}
                    dataKey={key}
                    stroke={colors[index % colors.length]}
                    fill={colors[index % colors.length]}
                    fillOpacity={0.2}
                  />
                ))}
              </AreaChart>
            ) : (
              <LineChart data={rows}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                <XAxis dataKey={xKey} stroke={palette.axis} fontSize={11} />
                <YAxis stroke={palette.axis} fontSize={11} />
                <Tooltip />
                {series.map((key, index) => (
                  <Line
                    key={key}
                    dataKey={key}
                    stroke={colors[index % colors.length]}
                    dot={false}
                  />
                ))}
              </LineChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </figure>
  );
}
