"use client";

import type { LucideIcon } from "lucide-react";
import { CircleHelp } from "lucide-react";

export function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className={`badge badge-${value.toLowerCase().replace(/[^a-z]+/g, "-")}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <CircleHelp size={26} strokeWidth={1.6} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

export function MetricCard({
  icon: Icon,
  label,
  value,
  context,
  tone = "blue",
}: {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  context: string;
  tone?: "blue" | "cyan" | "success" | "warning" | "danger";
}) {
  return (
    <div className={`metric-card metric-card-${tone}`}>
      <div className="metric-card-label">
        <span className="metric-icon">
          <Icon size={16} strokeWidth={1.9} />
        </span>
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      <small>{context}</small>
    </div>
  );
}
