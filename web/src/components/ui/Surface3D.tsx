import { useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";

type PlotComponent = ComponentType<Record<string, unknown>>;

async function loadPlotComponent(): Promise<PlotComponent> {
  const [{ default: Plotly }, { default: createPlotlyComponent }] =
    await Promise.all([
      import("plotly.js-gl3d-dist-min"),
      import("react-plotly.js/factory")
    ]);
  return createPlotlyComponent(Plotly) as PlotComponent;
}

type Surface3DProps = {
  title: string;
  z: number[][];
  x?: Array<number | string>;
  y?: Array<number | string>;
  axis?: {
    x_label?: string;
    y_label?: string;
    z_label?: string;
    x_unit?: string;
    y_unit?: string;
    z_unit?: string;
  };
  height?: number;
  className?: string;
  description?: string;
  howToRead?: string[];
  emptyMessage?: string;
};

export function Surface3D({
  title,
  z,
  x,
  y,
  axis,
  height = 320,
  className = "",
  description,
  howToRead = [],
  emptyMessage = "This surface needs more historical data before it can be shown."
}: Surface3DProps) {
  const [expanded, setExpanded] = useState(false);
  const [Plot, setPlot] = useState<PlotComponent | null>(null);
  const hasData = Array.isArray(z) && z.length > 0 && Array.isArray(z[0]) && z[0].length > 0;
  const expandedHeight = Math.max(height + 280, 520);
  const shouldLoadPlot = hasData;
  const axisLabel = (label: string | undefined, unit: string | undefined, fallback: string) =>
    [label || fallback, unit ? `(${unit})` : ""].filter(Boolean).join(" ");
  const xLabel = axisLabel(axis?.x_label, axis?.x_unit, "X");
  const yLabel = axisLabel(axis?.y_label, axis?.y_unit, "Y");
  const zLabel = axisLabel(axis?.z_label, axis?.z_unit, "Z");

  useEffect(() => {
    if (!shouldLoadPlot || Plot) return;
    let mounted = true;
    loadPlotComponent()
      .then((component) => {
        if (mounted) {
          setPlot(() => component);
        }
      })
      .catch(() => {
        if (mounted) {
          setPlot(null);
        }
      });
    return () => {
      mounted = false;
    };
  }, [Plot, shouldLoadPlot]);
  const data = hasData
    ? [
        {
          type: "surface",
          z,
          x,
          y,
          colorscale: [
            [0, "rgba(5,6,8,0.6)"],
            [0.25, "rgba(26,64,52,0.7)"],
            [0.55, "rgba(72,241,166,0.65)"],
            [1, "rgba(72,241,166,0.95)"]
          ],
          showscale: false,
          opacity: 0.92,
          lighting: {
            ambient: 0.45,
            diffuse: 0.85,
            specular: 0.45,
            roughness: 0.35,
            fresnel: 0.3
          },
          lightposition: { x: 120, y: 80, z: 180 },
          hovertemplate:
            `${xLabel}: %{x}<br>${yLabel}: %{y}<br>${zLabel}: %{z:.4f}<extra></extra>`
        }
      ]
    : [];

  const sceneLayout = useMemo(
    () => ({
      bgcolor: "rgba(0,0,0,0)",
      xaxis: {
        title: { text: xLabel, font: { size: 11, color: "#cbd5e1" } },
        showgrid: true,
        gridcolor: "rgba(72,241,166,0.08)",
        zerolinecolor: "rgba(72,241,166,0.2)",
        color: "#94a3b8"
      },
      yaxis: {
        title: { text: yLabel, font: { size: 11, color: "#cbd5e1" } },
        showgrid: true,
        gridcolor: "rgba(72,241,166,0.08)",
        zerolinecolor: "rgba(72,241,166,0.2)",
        color: "#94a3b8"
      },
      zaxis: {
        title: { text: zLabel, font: { size: 11, color: "#cbd5e1" } },
        showgrid: true,
        gridcolor: "rgba(72,241,166,0.08)",
        zerolinecolor: "rgba(72,241,166,0.2)",
        color: "#94a3b8"
      },
      camera: {
        eye: { x: 1.15, y: 1.15, z: 0.9 },
        center: { x: 0, y: 0, z: 0 }
      },
      aspectratio: { x: 1, y: 1, z: 0.6 }
    }),
    [xLabel, yLabel, zLabel]
  );

  const renderPlot = (plotHeight: number) => {
    if (!hasData) {
      return <div className="surface-empty">{emptyMessage}</div>;
    }
    if (!Plot) {
      return <div className="surface-empty">Loading 3D surface...</div>;
    }
    return (
      <Plot
        data={data as any}
        layout={{
          autosize: true,
          height: plotHeight,
          margin: { l: 0, r: 0, t: 0, b: 0 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          scene: sceneLayout,
          dragmode: "orbit"
        }}
        config={{ displayModeBar: false, displaylogo: false, responsive: true, scrollZoom: true }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler
      />
    );
  };

  return (
    <>
      <figure
        className={`glass-panel rounded-2xl p-5 surface-3d ${className}`}
        aria-label={title}
      >
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-100">{title}</p>
          <div className="flex items-center gap-3">
            <p className="text-[11px] text-emerald-300">{hasData ? "3D Surface" : "No data"}</p>
            <button
              className="text-[11px] text-slate-300 hover:text-emerald-300"
              type="button"
              onClick={() => setExpanded(true)}
            >
              Expand
            </button>
          </div>
        </div>
        {description ? <p className="mt-2 text-xs leading-5 text-slate-300">{description}</p> : null}
        <dl className="surface-axis-key" aria-label="Surface axes">
          <div><dt>X</dt><dd>{xLabel}</dd></div>
          <div><dt>Y</dt><dd>{yLabel}</dd></div>
          <div><dt>Z</dt><dd>{zLabel}</dd></div>
        </dl>
        <div className="mt-3">{renderPlot(height)}</div>
        {howToRead.length ? (
          <details className="visualization-details">
            <summary>How to read this</summary>
            <ul>
              {howToRead.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          </details>
        ) : null}
      </figure>
      {expanded ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-6"
          onClick={() => setExpanded(false)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setExpanded(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-label={`Expanded ${title}`}
        >
          <div
            className="w-full max-w-6xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="glass-panel rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-200">{title}</p>
                <button
                  className="text-xs text-slate-400 hover:text-emerald-300"
                  type="button"
                  onClick={() => setExpanded(false)}
                  autoFocus
                >
                  Close
                </button>
              </div>
              {description ? <p className="mt-2 text-xs leading-5 text-slate-300">{description}</p> : null}
              <dl className="surface-axis-key" aria-label="Surface axes">
                <div><dt>X</dt><dd>{xLabel}</dd></div>
                <div><dt>Y</dt><dd>{yLabel}</dd></div>
                <div><dt>Z</dt><dd>{zLabel}</dd></div>
              </dl>
              <div className="mt-4">{renderPlot(expandedHeight)}</div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
