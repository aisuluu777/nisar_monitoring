/** Мини-график смещения за последние циклы (см, с поправкой на сцену). */
export function Sparkline({ values, width = 120, height = 32, label }: { values: (number | null)[]; width?: number; height?: number; label?: string }) {
  const v = values.map((x) => (x === null || x === undefined ? null : x));
  const nums = v.filter((x): x is number => x !== null);
  if (nums.length < 2) return <span className="small muted">—</span>;
  const lo = Math.min(...nums, 0);
  const hi = Math.max(...nums, 0);
  const span = hi - lo || 1;
  const x = (i: number) => (i / (v.length - 1)) * (width - 4) + 2;
  const y = (val: number) => height - 3 - ((val - lo) / span) * (height - 6);
  let d = "";
  v.forEach((val, i) => {
    if (val === null) return;
    d += `${d && v[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(val).toFixed(1)}`;
  });
  const last = [...v].reverse().find((n) => n !== null) as number;
  const li = v.lastIndexOf(last);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label ?? "мини-график"}>
      <line x1="0" x2={width} y1={y(0)} y2={y(0)} stroke="rgba(159,195,214,.25)" strokeDasharray="2 3" />
      <path d={d} fill="none" stroke="#19E3FF" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(li)} cy={y(last)} r="3" fill="#19E3FF" />
    </svg>
  );
}
