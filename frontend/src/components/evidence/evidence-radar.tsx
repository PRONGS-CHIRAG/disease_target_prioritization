"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { DIMENSION_ORDER, type DimensionKey } from "@/lib/dimensions";

interface RadarPoint {
  dimension: DimensionKey;
  label: string;
  /** Plotted value — 0 for a null dimension, since a polygon vertex needs
   * SOME coordinate. `isMissing` is what actually distinguishes it. */
  value: number;
  isMissing: boolean;
}

/** A hollow, dashed marker for a dimension with no evidence, vs. a solid
 * filled dot for a real (possibly genuinely low) value — invariant 1's
 * "gap, not zero point" rendering, adapted to what a radar's geometry can
 * express: the vertex still has to sit somewhere, but it reads as visibly
 * different from a measured zero. */
function EvidenceDot(props: { cx?: number; cy?: number; payload?: RadarPoint }) {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined || !payload) return null;
  if (payload.isMissing) {
    return (
      <circle
        cx={cx}
        cy={cy}
        r={4}
        fill="var(--card)"
        stroke="var(--muted-foreground)"
        strokeWidth={1.5}
        strokeDasharray="2 2"
      />
    );
  }
  return <circle cx={cx} cy={cy} r={3} fill="var(--primary)" stroke="var(--card)" strokeWidth={1} />;
}

export function EvidenceRadar({
  dimensionValues,
  dimensionLabels,
}: {
  dimensionValues: Record<string, number | null | undefined>;
  dimensionLabels: Record<string, string>;
}) {
  const data: RadarPoint[] = DIMENSION_ORDER.map((dim) => {
    const raw = dimensionValues[dim];
    return {
      dimension: dim,
      label: dimensionLabels[dim] ?? dim,
      value: raw ?? 0,
      isMissing: raw === null || raw === undefined,
    };
  });

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="label"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          />
          <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
          <Radar
            dataKey="value"
            stroke="var(--primary)"
            fill="var(--primary)"
            fillOpacity={0.18}
            strokeWidth={2}
            dot={<EvidenceDot />}
            isAnimationActive={false}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const point = payload[0].payload as RadarPoint;
              return (
                <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 font-mono text-xs shadow-sm">
                  <div className="font-sans font-medium text-popover-foreground">{point.label}</div>
                  {point.isMissing ? (
                    <div className="text-muted-foreground">No evidence recorded</div>
                  ) : (
                    <div className="tabular-nums">{point.value.toFixed(3)}</div>
                  )}
                </div>
              );
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
