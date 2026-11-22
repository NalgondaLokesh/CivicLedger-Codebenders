import "./Landing.css";

// Persona presets. `persona` maps to the backend persona filter;
// `filters` are additionally applied to the Scheme Explorer on click.
export const PERSONAS = [
  {
    id: "students",
    title: "Students",
    icon: "🎓",
    description: "Post-matric, professional and overseas education support.",
    persona: "telangana_students",
    filters: {},
  },
  {
    id: "farmers",
    title: "Small Farmers",
    icon: "🌾",
    description: "Investment support and life insurance for cultivable-land farmers.",
    persona: "telangana_farmers",
    filters: {},
  },
  {
    id: "women_entrepreneurs",
    title: "Women Entrepreneurs",
    icon: "�",
    description: "SHG micro-credit, incubation and marriage assistance schemes.",
    persona: "telangana_women_entrepreneurs",
    filters: {},
  },
];

const TRUST_ITEMS = [
  {
    title: "Zero Data Logging",
    text: "No Aadhaar, PAN or other sensitive IDs are ever asked for or stored.",
  },
  {
    title: "Deterministic Rule Matching",
    text: "Every result follows published scheme rules you can read, not a black box.",
  },
  {
    title: "Direct Portal Links",
    text: "Each scheme links to its official portal with a last-verified date.",
  },
];

const STEPS = [
  {
    n: "1",
    title: "Tell us about you",
    text: "Answer a few questions — education level, category, family income. No IDs needed.",
  },
  {
    n: "2",
    title: "See your matches",
    text: "Rule-based results show Likely Eligible, Needs Clarification or Not Likely — with reasons.",
  },
  {
    n: "3",
    title: "Track your applications",
    text: "Save schemes, tick off documents and set reminders in your private tracker.",
  },
];

export default function Landing({ onCheckEligibility, onExplore, onPersona, schemeCount }) {
  const countLabel = typeof schemeCount === "number" ? String(schemeCount) : "—";

  return (
    <div className="landing">
      <header className="landing-masthead">
        <img className="landing-logo" src="/CivicLedger_Logo.jpg" alt="CivicLedger logo" />
        <p className="landing-kicker">Telangana State Civic Assistance</p>
      </header>

      <section className="landing-hero" aria-labelledby="landing-hero-title">
        <h1 id="landing-hero-title">Claim What's Yours</h1>
        <div className="landing-hero-aside">
          <p className="landing-lead">
            Find Telangana scholarships and fee support you may qualify for — post-matric,
            professional courses and study abroad. Free, private, and always linked to the
            official portal.
          </p>
          <div className="landing-actions">
            <button type="button" className="btn-primary" onClick={onCheckEligibility}>
              Check My Eligibility
            </button>
            <button type="button" className="btn-secondary" onClick={onExplore}>
              Explore All Schemes
            </button>
          </div>
          <p className="landing-note">Free account required · Results are indicative, never guaranteed</p>
        </div>
      </section>

      <section className="landing-steps" aria-labelledby="landing-steps-title">
        <h2 id="landing-steps-title" className="landing-label">How it works</h2>
        <ol className="landing-steps-list">
          {STEPS.map((s) => (
            <li className="landing-step" key={s.n}>
              <span className="landing-step-num" aria-hidden>{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-trust" aria-labelledby="landing-trust-title">
        <h2 id="landing-trust-title" className="landing-label">Why CivicLedger</h2>
        <ul className="landing-trust-list">
          {TRUST_ITEMS.map((item) => (
            <li className="landing-trust-item" key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="landing-section" aria-labelledby="personas-heading">
        <div className="landing-section-head">
          <h2 id="personas-heading">Start with your situation</h2>
          <p className="landing-sub">Pick a profile to see the schemes that usually apply.</p>
        </div>
        <ul className="landing-personas">
          {PERSONAS.map((p, i) => (
            <li key={p.id}>
              <button
                type="button"
                className="landing-persona"
                onClick={() => onPersona(p.id)}
              >
                <span className="landing-persona-index" aria-hidden>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="landing-persona-title">{p.title}</span>
                <span className="landing-persona-desc">{p.description}</span>
                <span className="landing-persona-cta">View schemes →</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="landing-figures" aria-label="Key figures">
        <div className="landing-metric">
          <strong>{countLabel}</strong>
          <span>Verified schemes</span>
        </div>
        <div className="landing-metric">
          <strong>&lt; 30 sec</strong>
          <span>Average check time</span>
        </div>
        <div className="landing-metric">
          <strong>Free</strong>
          <span>Open access</span>
        </div>
      </section>

      <p className="landing-foot">
        No Aadhaar or PAN is collected. Eligibility results are indicative only and never a guarantee of benefit.
      </p>
    </div>
  );
}
