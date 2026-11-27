// Diverging blue–white–red scale (ColorBrewer RdBu end points), symmetric around 0.
const BLUE: [number, number, number] = [33, 102, 172];
const WHITE: [number, number, number] = [247, 247, 247];
const RED: [number, number, number] = [178, 24, 43];

function mix(a: [number, number, number], b: [number, number, number], t: number): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** Colour for a log2 fold change, scaled so that +/-maxAbs map to full red/blue. */
export function divergingColor(value: number, maxAbs: number): string {
  const t = Math.max(-1, Math.min(1, maxAbs > 0 ? value / maxAbs : 0));
  return t < 0 ? mix(WHITE, BLUE, -t) : mix(WHITE, RED, t);
}
