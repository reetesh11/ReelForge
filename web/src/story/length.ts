function fmt(n: number): string {
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** "Estimated length: 11.5 s of 12 s target", or the over-target wording. */
export function estimateLength(durations: ReadonlyArray<number | null | undefined>, target: number): string {
  let total = 0;
  let missing = 0;
  for (const d of durations) {
    if (typeof d === "number") total += d;
    else missing += 1;
  }
  const suffix = missing > 0 ? ` (${missing} scene${missing === 1 ? " has" : "s have"} no duration yet)` : "";
  if (total > target + 0.05) return `Over target by ${fmt(total - target)} s${suffix}`;
  return `Estimated length: ${fmt(total)} s of ${fmt(target)} s target${suffix}`;
}
