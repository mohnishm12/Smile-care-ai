"use client";

import DemoButton from "./DemoButton";

const LINKS = [
  { href: "#brief", label: "The Brief" },
  { href: "#receptionist", label: "Receptionist" },
  { href: "#recovery", label: "Recovery" },
  { href: "#trust", label: "Trust" },
];

export default function Nav() {
  return (
    <header className="mrd-nav">
      <div className="mrd-nav-inner">
        <a href="#top" className="mrd-wordmark" aria-label="Meridian home">
          <span className="mrd-wordmark-dot" aria-hidden="true" />
          Meridian
        </a>
        <nav className="mrd-nav-links" aria-label="Sections">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="mrd-nav-cta">
          <DemoButton label="Try the demo" />
        </div>
      </div>
    </header>
  );
}
