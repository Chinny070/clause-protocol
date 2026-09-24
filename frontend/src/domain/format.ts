const GEN = 10n ** 18n;

/** Exact GEN formatting from atoms (no floating point). Trailing zeros trimmed; at most `maxDecimals` shown. */
export function formatGen(atoms: bigint, maxDecimals = 6): string {
  const neg = atoms < 0n;
  const a = neg ? -atoms : atoms;
  const whole = a / GEN;
  const frac = a % GEN;
  let fracStr = frac.toString().padStart(18, "0");
  if (maxDecimals < 18) fracStr = fracStr.slice(0, maxDecimals);
  fracStr = fracStr.replace(/0+$/, "");
  const wholeStr = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${neg ? "-" : ""}${wholeStr}${fracStr ? "." + fracStr : ""}`;
}

/** Parses a user-entered decimal GEN amount into atoms. Returns null for anything that is not a plain positive decimal. */
export function parseGen(input: string): bigint | null {
  const t = input.trim();
  if (!/^\d+(\.\d{1,18})?$/.test(t)) return null;
  const [w, f = ""] = t.split(".");
  return BigInt(w) * GEN + BigInt(f.padEnd(18, "0"));
}

export function formatUtc(unixSeconds: number): string {
  if (!unixSeconds) return "not set";
  const d = new Date(unixSeconds * 1000);
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

export function formatDate(unixSeconds: number): string {
  if (!unixSeconds) return "not set";
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export function formatDuration(seconds: number): string {
  if (seconds <= 0) return "0s";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const parts: string[] = [];
  if (d) parts.push(`${d}d`);
  if (h) parts.push(`${h}h`);
  if (m && !d) parts.push(`${m}m`);
  if (s && !d && !h) parts.push(`${s}s`);
  return parts.join(" ") || "0s";
}

export function shortHex(hex: string, head = 6, tail = 4): string {
  if (hex.length <= head + tail + 1) return hex;
  return `${hex.slice(0, head)}…${hex.slice(-tail)}`;
}

export function sameAddress(a: string | undefined | null, b: string | undefined | null): boolean {
  return !!a && !!b && a.toLowerCase() === b.toLowerCase();
}

export function bpsToPercent(bps: number): string {
  return `${(bps / 100).toFixed(bps % 100 === 0 ? 0 : 2)}%`;
}
