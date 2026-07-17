import { useCallback, useRef, useState, type ReactNode } from "react";

type Props = {
  domain: [number, number];
  onRangeSelected: (startMs: number, endMs: number) => void;
  children: ReactNode;
};

type DragState = {
  startX: number;
  currentX: number;
};

const MIN_DRAG_PX = 8;

export function ChartRangeBrush({ domain, onRangeSelected, children }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);

  const pixelToTime = useCallback(
    (clientX: number): number | null => {
      // Map against the X-axis line itself, not the full SVG surface: the
      // surface includes the Y-axis label gutters and chart margins, so
      // using its full width as the domain's pixel span shifts every
      // selection by however wide those side gutters are — proportionally
      // worse for wide time ranges (e.g. "Last day") than for narrow ones,
      // which is what made this look like a timezone bug.
      const axisLine = containerRef.current?.querySelector(
        ".recharts-xAxis .recharts-cartesian-axis-line",
      );
      const rect =
        axisLine?.getBoundingClientRect() ??
        containerRef.current?.querySelector(".recharts-surface")?.getBoundingClientRect() ??
        containerRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0) {
        return null;
      }
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const [min, max] = domain;
      return min + ratio * (max - min);
    },
    [domain],
  );

  const finishDrag = useCallback(
    (state: DragState) => {
      const startTime = pixelToTime(state.startX);
      const endTime = pixelToTime(state.currentX);
      if (startTime == null || endTime == null) {
        return;
      }
      if (Math.abs(state.currentX - state.startX) < MIN_DRAG_PX) {
        return;
      }
      onRangeSelected(startTime, endTime);
    },
    [onRangeSelected, pixelToTime],
  );

  const selectionStyle = drag
    ? (() => {
        const left = Math.min(drag.startX, drag.currentX);
        const width = Math.abs(drag.currentX - drag.startX);
        const containerRect = containerRef.current?.getBoundingClientRect();
        if (!containerRect) {
          return undefined;
        }
        return {
          left: left - containerRect.left,
          width,
        };
      })()
    : undefined;

  return (
    <div
      className="relative h-full w-full select-none"
      ref={containerRef}
      onMouseLeave={() => {
        if (drag) {
          finishDrag(drag);
          setDrag(null);
        }
      }}
      onMouseDown={(e) => {
        if (e.button !== 0) {
          return;
        }
        setDrag({ startX: e.clientX, currentX: e.clientX });
      }}
      onMouseMove={(e) => {
        if (!drag) {
          return;
        }
        setDrag({ ...drag, currentX: e.clientX });
      }}
      onMouseUp={(e) => {
        if (!drag) {
          return;
        }
        const final = { ...drag, currentX: e.clientX };
        finishDrag(final);
        setDrag(null);
      }}
    >
      {children}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 5 }}
      />
      {selectionStyle && selectionStyle.width >= MIN_DRAG_PX ? (
        <div
          className="pointer-events-none absolute top-0 z-20 h-full border border-brand-600 bg-brand-500/20"
          style={selectionStyle}
        />
      ) : null}
      <p className="pointer-events-none absolute bottom-1 left-2 z-20 text-[10px] text-slate-500">
        Drag on chart to select time range
      </p>
    </div>
  );
}
