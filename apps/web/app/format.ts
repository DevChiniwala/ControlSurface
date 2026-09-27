export function displayDate(value: string | undefined | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export function displayRelativeDate(value: string | undefined | null) {
  if (!value) return "—";
  const delta = Date.now() - Date.parse(value);
  if (!Number.isFinite(delta)) return displayDate(value);
  const minutes = Math.max(0, Math.floor(delta / 60_000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function displayUsd(nano: number | undefined | null, digits = 4) {
  return nano == null ? "—" : `$${(nano / 1_000_000_000).toFixed(digits)}`;
}

export function displayDuration(ms: number | undefined | null) {
  if (ms == null) return "—";
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(2)}s`;
  return `${ms.toFixed(0)}ms`;
}

export function displayTokens(value: number | undefined | null) {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toLocaleString();
}

export function displayPercent(value: number | undefined | null, digits = 1) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function shortId(id: string | undefined | null, length = 10) {
  return id ? `${id.slice(0, length)}…` : "—";
}

export function displayDelta(
  value: number | undefined | null,
  options: { percent?: boolean; suffix?: string; digits?: number } = {},
) {
  if (value == null) return "—";
  const amount = options.percent ? value * 100 : value;
  const sign = amount > 0 ? "+" : "";
  return `${sign}${amount.toFixed(options.digits ?? 1)}${options.percent ? "%" : options.suffix || ""}`;
}
