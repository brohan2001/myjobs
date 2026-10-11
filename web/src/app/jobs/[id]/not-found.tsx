import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

export default function JobNotFound() {
  return (
    <div className="wrap">
      <header>
        <div className="top">
          <p className="brand">
            <Link href="/">myjobs</Link>
          </p>
          <ThemeToggle />
        </div>
      </header>

      <main className="detail">
        <Link href="/" className="back-link">
          ← Back to feed
        </Link>
        <div className="state state-empty" role="status">
          <p className="state-h">We couldn&apos;t find that job.</p>
          <p className="state-p">
            It might have expired or been removed from the company career board.
          </p>
          <div className="state-b">
            <Link href="/" className="btn">
              Browse newest jobs
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
