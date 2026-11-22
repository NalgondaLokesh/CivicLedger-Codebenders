import { useEffect, useMemo, useState } from "react";
import { fetchSchemes, fetchMe, logout } from "./api.js";
import EligibilityChat from "./components/EligibilityChat.jsx";
import ApplicationTracker from "./components/ApplicationTracker.jsx";
import Landing, { PERSONAS } from "./components/Landing.jsx";
import AuthPanel, { readSession, writeSession, clearSession } from "./components/AuthPanel.jsx";
import AdminPanel from "./components/AdminPanel.jsx";
import Welcome from "./components/Welcome.jsx";

// Header tabs. "auth" is reached from the account pill, not from the tab bar.
const TABS = [
  { id: "explore", label: "Scheme Explorer" },
  { id: "ai", label: "AI Eligibility Check", tag: "Prompt" },
  { id: "tracker", label: "Application Tracker" },
];

const EDUCATION_LEVELS = [
  { value: "", label: "All levels" },
  { value: "post_matric", label: "Post-Matric" },
  { value: "professional", label: "Professional" },
  { value: "overseas", label: "Overseas" },
];

const CATEGORIES = [
  { value: "", label: "All categories" },
  { value: "sc", label: "SC" },
  { value: "st", label: "ST" },
  { value: "bc", label: "BC" },
  { value: "ebc", label: "EBC" },
  { value: "minority", label: "Minority" },
  { value: "general", label: "General" },
];

const INCOME_STEPS = [0, 100000, 150000, 200000, 250000, 300000, 400000, 500000];

const PERSONA_OPTIONS = [
  { value: "", label: "All personas" },
  { value: "telangana_students", label: "Students" },
  { value: "telangana_farmers", label: "Small Farmers" },
  { value: "telangana_women_entrepreneurs", label: "Women Entrepreneurs" },
];

const LEVEL_OPTIONS = [
  { value: "", label: "State + Central" },
  { value: "state", label: "State schemes" },
  { value: "central", label: "Central schemes" },
];
const formatINR = (n) =>
  n >= 100000 ? `₹${(n / 100000).toFixed(n % 100000 ? 1 : 0)}L` : `₹${n.toLocaleString("en-IN")}`;

const CATEGORY_LABELS = {
  sc: "SC", st: "ST", bc: "BC", ebc: "EBC",
  minority: "Minority", general: "General", all: "All",
};
const LEVEL_LABELS = {
  post_matric: "Post-Matric", professional: "Professional", overseas: "Overseas",
};

function SchemeCard({ scheme }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="card">
      <div className="card-top">
        <span className="chip chip-level">{LEVEL_LABELS[scheme.education_level] || scheme.education_level}</span>
        <span className="chip chip-cat">{CATEGORY_LABELS[scheme.category] || scheme.category}</span>
        {scheme.scheme_level === "central" && <span className="chip chip-central">Central</span>}
        <span className="chip chip-verified" title={`Last verified ${scheme.last_verified_date}`}>
          ✓ {scheme.last_verified_date}
        </span>
      </div>
      <h3>{scheme.name}</h3>
      <p className="summary">{scheme.summary}</p>
      <div className="likely-tag">Likely Eligible · Indicative only</div>
      {scheme.amount_or_benefit && <p className="benefit">💰 {scheme.amount_or_benefit}</p>}

      <div className="rules">
        {scheme.rules.map((r, i) => (
          <div className="rule" key={i}>
            <span className="rule-label">{r.label}</span>
            <span className="rule-value">{r.value}</span>
          </div>
        ))}
      </div>

      <button className="link-btn" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
        {expanded ? "Hide details ▴" : "Documents & steps ▾"}
      </button>

      {expanded && (
        <div className="card-details">
          <h4>Required documents</h4>
          <ul className="doc-list">
            {scheme.required_documents.map((d) => <li key={d}>{d}</li>)}
          </ul>
          <h4>How to apply</h4>
          <ol className="step-list">
            {scheme.application_steps.map((s) => <li key={s}>{s}</li>)}
          </ol>
        </div>
      )}

      <a className="official-link" href={scheme.official_url} target="_blank" rel="noreferrer">
        Official portal ↗
      </a>
    </article>
  );
}

const VALID_VIEWS = new Set([...TABS.map((t) => t.id), "auth", "welcome"]);

function viewFromHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  return VALID_VIEWS.has(h) ? h : "landing";
}

export default function App() {
  // Hash-based routing: refresh keeps the tab, views are deep-linkable.
  const [view, setViewState] = useState(viewFromHash);
  const [selectedPersona, setSelectedPersona] = useState(null);
  const [session, setSession] = useState(() => readSession());
  const [disclaimerHidden, setDisclaimerHidden] = useState(() => {
    try { return localStorage.getItem("civicledger_disclaimer_hidden") === "1"; } catch { return false; }
  });
  const [totalSchemes, setTotalSchemes] = useState(null);
  const [educationLevel, setEducationLevel] = useState("");
  const [category, setCategory] = useState("");
  const [persona, setPersona] = useState("");
  const [schemeLevel, setSchemeLevel] = useState("");
  const [incomeIdx, setIncomeIdx] = useState(0);
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [schemesVersion, setSchemesVersion] = useState(0);
  const [adminOpen, setAdminOpen] = useState(false);

  const maxIncome = INCOME_STEPS[incomeIdx] || null;

  // Unfiltered scheme count for the header tab and the Landing metrics.
  useEffect(() => {
    let cancelled = false;
    fetchSchemes()
      .then((data) => {
        if (!cancelled) setTotalSchemes(Array.isArray(data.items) ? data.items.length : null);
      })
      .catch(() => {
        if (!cancelled) setTotalSchemes(null);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchSchemes({
      educationLevel: educationLevel || undefined,
      category: category || undefined,
      persona: persona || undefined,
      schemeLevel: schemeLevel || undefined,
      maxIncome: maxIncome || undefined,
    })
      .then((data) => { setSchemes(data.items); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [educationLevel, category, persona, schemeLevel, maxIncome, schemesVersion]);

  const visibleSchemes = useMemo(() => schemes, [schemes]);

  const [pendingView, setPendingView] = useState(null);

  // Gate a target view behind sign-in; returns the view to actually show.
  const gateView = (v) => {
    if (!session && v !== "landing" && v !== "auth") {
      setPendingView(v);
      return "auth";
    }
    return v;
  };

  const setView = (v) => {
    v = gateView(v);
    setViewState(v);
    window.location.hash = v;
  };

  useEffect(() => {
    const onHash = () => {
      const target = gateView(viewFromHash());
      setViewState(target);
      if (target !== viewFromHash()) window.location.hash = target;
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // Validate a stored session token on load; drop it if the server rejects it.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    fetchMe().then((me) => {
      if (!cancelled && !me) {
        clearSession();
        setSession(null);
      }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSessionChange = (next) => {
    if (next) {
      writeSession(next);
    } else {
      logout(); // revoke the server session, then clear locally
      clearSession();
    }
    setSession(next);
    if (next) {
      // After sign-in, show the welcome screen; pendingView is where the
      // user was headed and is used by the welcome actions.
      setViewState("welcome");
      window.location.hash = "welcome";
    } else {
      setPendingView(null);
      // Sign-out always lands back on the public Landing page.
      setViewState("landing");
      window.location.hash = "landing";
    }
  };

  const handlePersona = (id) => {
    const p = PERSONAS.find((x) => x.id === id);
    setSelectedPersona(id);
    if (p?.persona) setPersona(p.persona);
    if (p?.filters) {
      setEducationLevel(p.filters.education_level ?? "");
      setCategory(p.filters.category ?? "");
      setIncomeIdx(0);
    }
    setView("explore");
  };

  const personaTitle = PERSONAS.find((p) => p.id === selectedPersona)?.title;
  const accountLabel = session ? session.user.displayName : "Sign In";
  // Landing is pre-login only — it's not a tab; signed-out users land there
  // and feature tabs gate to the sign-in panel.
  const tabs = TABS;
  // Signed-in users never see Landing; signed-out users only see Landing/Auth.
  const activeView = session
    ? (view === "landing" ? "explore" : view)
    : (view === "landing" || view === "auth" ? view : "auth");

  return (
    <>
      <div className="site-chrome">
        {!disclaimerHidden && (
          <div className="disclaimer-bar" role="note">
            🛡️ <strong>Indicative eligibility only</strong> ("Likely Eligible", never guaranteed) •
            No Aadhaar or sensitive IDs collected.
            <button
              type="button"
              className="disclaimer-dismiss"
              aria-label="Dismiss notice"
              onClick={() => {
                setDisclaimerHidden(true);
                try { localStorage.setItem("civicledger_disclaimer_hidden", "1"); } catch {}
              }}
            >
              ×
            </button>
          </div>
        )}

        <header className="topbar">
          <div className="topbar-left">
            <div className="brand">
              <img className="brand-logo" src="/CivicLedger_Logo.jpg" alt="CivicLedger logo" />
              <span className="wordmark">CivicLedger</span>
            </div>
            <span className="portal-badge">Telangana Portal</span>
          </div>

          <div className="topbar-right">
            <span className="location-badge">Telangana State Services</span>
            <button
              type="button"
              className="admin-toggle-btn"
              onClick={() => setAdminOpen((o) => !o)}
              aria-expanded={adminOpen}
            >
              Admin
            </button>
            <div className="account-pill">
              <button
                type="button"
                className={activeView === "auth" ? "account-pill-btn active" : "account-pill-btn"}
                onClick={() => setView("auth")}
                aria-current={activeView === "auth" ? "page" : undefined}
              >
                {accountLabel}
              </button>
            </div>
          </div>

          <nav className="tab-bar" aria-label="Sections">
            {tabs.map((t) => {
              const active = activeView === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  className={active ? "tab-btn active" : "tab-btn"}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setView(t.id)}
                >
                  {t.label}
                  {t.id === "explore" && typeof totalSchemes === "number" && (
                    <span className="tab-count">{totalSchemes}</span>
                  )}
                  {t.tag && <span className="tab-tag">{t.tag}</span>}
                </button>
              );
            })}
          </nav>
        </header>
      </div>

      {adminOpen && (
        <AdminPanel
          onClose={() => setAdminOpen(false)}
          onSaved={() => setSchemesVersion((v) => v + 1)}
        />
      )}

      <div className="app">
        <main>
          {activeView === "landing" && (
            <Landing
              onCheckEligibility={() => setView("ai")}
              onExplore={() => setView("explore")}
              onPersona={handlePersona}
              schemeCount={totalSchemes}
            />
          )}

          {activeView === "explore" && (
            <section id="explore" className="explorer">
              <h1>Scheme Explorer</h1>
              <p className="muted">
                {personaTitle
                  ? <>Profile selected: <strong>{personaTitle}</strong>. </>
                  : null}
                Scholarships & fee support for Telangana students.
              </p>

              <div className="filter-bar" role="search">
                <label className="filter">
                  <span>Persona</span>
                  <select value={persona} onChange={(e) => setPersona(e.target.value)}>
                    {PERSONA_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <label className="filter">
                  <span>Education level</span>
                  <select value={educationLevel} onChange={(e) => setEducationLevel(e.target.value)}>
                    {EDUCATION_LEVELS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <label className="filter">
                  <span>Level</span>
                  <select value={schemeLevel} onChange={(e) => setSchemeLevel(e.target.value)}>
                    {LEVEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <label className="filter">
                  <span>Category</span>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    {CATEGORIES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <label className="filter">
                  <span>Family income up to {incomeIdx === 0 ? "any" : formatINR(maxIncome)}</span>
                  <input
                    type="range"
                    min={0}
                    max={INCOME_STEPS.length - 1}
                    step={1}
                    value={incomeIdx}
                    onChange={(e) => setIncomeIdx(Number(e.target.value))}
                    aria-label="Maximum family income"
                  />
                </label>
              </div>

              {loading && (
                <div className="card-grid" aria-busy="true" aria-label="Loading schemes">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="skeleton-card">
                      <div className="skeleton-line short" />
                      <div className="skeleton-line med" />
                      <div className="skeleton-line long" />
                      <div className="skeleton-line long" />
                    </div>
                  ))}
                </div>
              )}
              {error && <p className="status error">⚠️ {error} — is the backend running?</p>}
              {!loading && !error && visibleSchemes.length === 0 && (
                <p className="status">No schemes match these filters.</p>
              )}

              {!loading && !error && (
                <div className="card-grid">
                  {visibleSchemes.map((s) => <SchemeCard key={s.slug || s.name} scheme={s} />)}
                </div>
              )}
            </section>
          )}

          {activeView === "ai" && <EligibilityChat />}
          {activeView === "tracker" && <ApplicationTracker onGoToChat={() => setView("ai")} />}

          {activeView === "welcome" && session && (
            <Welcome
              name={session.user.displayName}
              onNavigate={(v) => {
                setPendingView(null);
                setView(v);
              }}
            />
          )}

          {activeView === "auth" && (
            <AuthPanel
              session={session}
              onSessionChange={handleSessionChange}
              onExplore={() => setView("explore")}
            />
          )}
        </main>

        <footer className="footer">
          <p>CivicLedger is an informational aid. Always verify rules on the official portal before applying.</p>
        </footer>
      </div>
    </>
  );
}
