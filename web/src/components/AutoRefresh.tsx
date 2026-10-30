"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-renders the server component on an interval, so live stats stay current without a reload. */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
