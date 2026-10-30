import type { Metadata } from "next";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Admin - myjobs",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="wrap">
      <header>
        <div className="top">
          <p className="brand">
            <Link href="/">myjobs</Link> <span className="admin-badge">admin</span>
          </p>
          <ThemeToggle />
        </div>
        <nav className="admin-nav" aria-label="Admin">
          <Link href="/admin">Overview</Link>
          <Link href="/admin/boards">Boards</Link>
          <Link href="/admin/errors">Errors</Link>
          <Link href="/coverage">Public coverage</Link>
        </nav>
      </header>
      <main className="coverage-page">{children}</main>
    </div>
  );
}
