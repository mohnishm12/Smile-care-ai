import DemoButton from "./DemoButton";

export default function CtaFooter() {
  return (
    <section className="mrd-cta-section" id="try">
      <div className="mrd-cta-glow" aria-hidden="true" />
      <div className="mrd-cta-inner">
        <h2 className="mrd-cta-title">
          Meet the employee who <span className="mrd-grad">never clocks in.</span>
        </h2>
        <p className="mrd-cta-sub">
          Spin up a fully seeded demo clinic in seconds and walk in to a live
          Morning Brief — real patients, real decisions, waiting for you.
        </p>
        <DemoButton label="Try the demo clinic" size="lg" />
      </div>

      <footer className="mrd-footer">
        <a href="#top" className="mrd-wordmark" aria-label="Meridian home">
          <span className="mrd-wordmark-dot" aria-hidden="true" />
          Meridian
        </a>
        <span className="mrd-footer-meta">
          The clinic operating system &middot;{" "}
          <a href="/login" className="mrd-footer-link">
            Staff sign in
          </a>
        </span>
      </footer>
    </section>
  );
}
