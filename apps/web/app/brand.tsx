"use client";

import { useId } from "react";

export function BrandMark({ className = "" }: { className?: string }) {
  const gradientId = useId().replace(/:/g, "");

  return (
    <svg
      className={`brand-symbol ${className}`.trim()}
      viewBox="0 0 160 132"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient
          id={gradientId}
          x1="59"
          y1="37"
          x2="144"
          y2="111"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#35C2FF" />
          <stop offset="0.55" stopColor="#247CFF" />
          <stop offset="1" stopColor="#4F6FFF" />
        </linearGradient>
      </defs>
      <path
        fill="currentColor"
        d="M139 6H70C31 6 7 32 7 68c0 35 25 58 62 58h5c15 0 24-3 34-12l18-16c8-7 3-20-8-20H69c-17 0-27-10-27-25 0-16 12-27 29-27h11c9 0 15-2 21-8L139 6Z"
      />
      <path
        fill={`url(#${gradientId})`}
        d="M82 46c14-15 28-22 45-19 21 3 33 21 33 45 0 25-15 46-35 55 9-25 4-44-18-47H67c-14 0-20-13-11-24l26-10Z"
      />
    </svg>
  );
}

export function BrandIdentity({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`brand-identity ${compact ? "brand-identity-compact" : ""}`}
    >
      <BrandMark />
      <span className="brand-wordmark">
        Control<span>Surface</span>
      </span>
    </div>
  );
}
