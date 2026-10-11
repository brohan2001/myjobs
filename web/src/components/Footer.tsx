import Link from "next/link";

export function Footer() {
  return (
    <footer className="footer" role="contentinfo">
      <p className="footer-note">
        Jobs come from public company career pages. Updated continuously.
      </p>
      <p className="footer-links">
        <Link href="/coverage">Coverage</Link>
        <span className="footer-sep"> · </span>
        <a
          href="https://github.com/brohan2001/myjobs"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub
        </a>
      </p>
    </footer>
  );
}
