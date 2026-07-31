/**
 * A row of instrument-panel-style stat readouts — large monospace figures
 * under small-caps labels, separated by hairlines rather than boxed into
 * individual KPI cards. Part of the "instrument panel" design direction
 * (frontend-design skill, milestone5_plan.md §2.4): the page reads the
 * disease's own numbers the way a lab instrument displays a measurement,
 * not as a generic icon-plus-number dashboard tile.
 */
export function ReadoutStrip({
  items,
}: {
  items: { label: string; value: string; caption?: string }[];
}) {
  return (
    <div className="grid grid-cols-1 divide-y divide-border rounded-md border border-border bg-card sm:grid-cols-3 sm:divide-x sm:divide-y-0">
      {items.map((item) => (
        <div key={item.label} className="px-5 py-4">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            {item.label}
          </div>
          <div className="mt-1 font-mono text-2xl font-medium tabular-nums">{item.value}</div>
          {item.caption && <div className="mt-0.5 text-xs text-muted-foreground">{item.caption}</div>}
        </div>
      ))}
    </div>
  );
}
