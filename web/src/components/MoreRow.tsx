"use client";

import Link from "next/link";

interface MoreRowProps {
  company: { slug: string; name: string };
  count: number;
  index: number;
  isFocused?: boolean;
  onFocus?: () => void;
  onExpand: () => void;
  companyHref: string;
}

export function MoreRow({
  company,
  count,
  index,
  isFocused = false,
  onFocus,
  onExpand,
  companyHref,
}: MoreRowProps) {
  return (
    <li
      className={`row row-more ${isFocused ? "focused" : ""}`}
      data-i={index}
      tabIndex={isFocused ? 0 : -1}
      onFocus={onFocus}
      role="button"
      aria-label={`+${count} more from ${company.name}, click to expand`}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("a")) {
          return;
        }
        onExpand();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if ((e.target as HTMLElement).tagName.toLowerCase() !== "a") {
            e.preventDefault();
            onExpand();
          }
        }
      }}
    >
      <div className="more-content">
        <span className="more-text">
          +{count} more from {company.name}
        </span>
        <span className="more-sep" aria-hidden="true">
          ·
        </span>
        <Link
          href={companyHref}
          className="more-company-link"
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          only this company
        </Link>
      </div>
    </li>
  );
}
