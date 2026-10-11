export interface Salary {
  min: number;
  max: number | null;
  currency: string;
  period: string;
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 60) {
    return "just now";
  }

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) {
    return `${diffMin} min ago`;
  }

  const nowUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const dateUtc = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  const dayDiff = Math.floor((nowUtc - dateUtc) / (24 * 60 * 60 * 1000));

  if (dayDiff === 0) {
    const diffHours = Math.floor(diffSec / 3600);
    return `${diffHours} h ago`;
  }

  if (dayDiff === 1) {
    return "yesterday";
  }

  return `${dayDiff} days ago`;
}

export function timeBucket(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec <= 3600) {
    return "last hour";
  }

  const nowUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const dateUtc = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  const dayDiff = Math.floor((nowUtc - dateUtc) / (24 * 60 * 60 * 1000));

  if (dayDiff === 0) {
    return "earlier today";
  }

  if (dayDiff === 1) {
    return "yesterday";
  }

  if (dayDiff <= 7) {
    return "this week";
  }

  return "older";
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

export function formatSalary(
  salary: Salary | null | undefined,
  targetCurrency: string,
  rates: Record<string, number>
): string | null {
  if (!salary || salary.min == null) {
    return null;
  }

  const activeCurrency =
    targetCurrency === "native" ? salary.currency : targetCurrency;
  const isConverted = activeCurrency !== salary.currency;

  const fromRate = rates[salary.currency] ?? 1;
  const toRate = rates[activeCurrency] ?? 1;
  const convert = (val: number) => (val * fromRate) / toRate;

  const minVal = isConverted ? convert(salary.min) : salary.min;
  const maxVal =
    salary.max != null
      ? isConverted
        ? convert(salary.max)
        : salary.max
      : null;

  const approxPrefix = isConverted ? "≈ " : "";
  const isYearly = salary.period === "yearly" || salary.period === "year";
  const isMonthly = salary.period === "monthly" || salary.period === "month";

  if (activeCurrency === "INR") {
    if (isMonthly) {
      const formatMonthly = (v: number) => Math.round(v).toLocaleString("en-IN");
      const range =
        maxVal != null && maxVal !== minVal
          ? `${formatMonthly(minVal)}–${formatMonthly(maxVal)}`
          : formatMonthly(minVal);
      return `${approxPrefix}₹${range} / month`;
    }

    // Default to LPA (yearly)
    const formatLpa = (v: number) => {
      const l = v / 100000;
      return Number(l.toFixed(1)).toString();
    };

    const range =
      maxVal != null && maxVal !== minVal
        ? `${formatLpa(minVal)}–${formatLpa(maxVal)}`
        : formatLpa(minVal);
    return `${approxPrefix}₹${range} LPA`;
  }

  const sym = CURRENCY_SYMBOLS[activeCurrency] ?? `${activeCurrency} `;

  if (isYearly) {
    const minK = Math.round(minVal / 1000);
    const maxK = maxVal != null ? Math.round(maxVal / 1000) : null;
    const range =
      maxK != null && maxK !== minK ? `${minK}k–${maxK}k` : `${minK}k`;
    return `${approxPrefix}${sym}${range} / yr`;
  }

  // Monthly or other
  const formatNum = (v: number) => Math.round(v).toLocaleString("en-US");
  const range =
    maxVal != null && maxVal !== minVal
      ? `${formatNum(minVal)}–${formatNum(maxVal)}`
      : formatNum(minVal);
  return `${approxPrefix}${sym}${range} / ${salary.period}`;
}
