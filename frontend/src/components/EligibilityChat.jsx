import { useEffect, useRef, useState } from "react";
import { createTrackerItem, fetchChatHistory, clearChatHistory, postEligibilityChat } from "../api.js";
import Markdown from "./Markdown.jsx";
import "./EligibilityChat.css";

const WELCOME =
  "Hi! Tell me about your studies, category, family income and state, and I'll suggest schemes you may be likely eligible for.";

const SAMPLE_STORIES = [
  {
    label: "SC student, Warangal",
    text: "I'm a SC student from Warangal, completed intermediate, family income about 1.5 lakh a year, want a post-matric scholarship.",
  },
  {
    label: "BC engineering student",
    text: "I'm a BC final-year engineering student from Hyderabad, my family earns around 2 lakh, I got admission in a private college.",
  },
  {
    label: "Minority, study abroad",
    text: "I'm planning to study abroad for a master's, from a minority community family in Karimnagar, income under 6 lakh.",
  },
  {
    label: "Small farmer",
    text: "I own 2 acres of cultivable land in Karimnagar, aged 42, looking for crop investment support and insurance.",
  },
  {
    label: "Woman entrepreneur",
    text: "I am part of a SERP-registered SHG in Warangal looking to set up a food processing unit with micro-credit support.",
  },
];

const PERSONA_OPTIONS = [
  { value: "", label: "Auto-detect persona" },
  { value: "telangana_students", label: "Students" },
  { value: "telangana_farmers", label: "Small Farmers" },
  { value: "telangana_women_entrepreneurs", label: "Women Entrepreneurs" },
];

const PERSONA_LABELS = {
  telangana_students: "Students",
  telangana_farmers: "Small Farmers",
  telangana_women_entrepreneurs: "Women Entrepreneurs",
};

const TRAIT_LABELS = {
  education_level: "Education",
  category: "Category",
  annual_income: "Income",
  state: "State",
  needs_overseas: "Overseas",
  age: "Age",
  gender: "Gender",
  has_cultivable_land: "Cultivable land",
  shg_member: "SHG member",
  persona: "Persona",
};

const BADGE_TEXT = {
  likely_eligible: "Likely Eligible",
  needs_clarification: "Needs Clarification",
  not_likely: "Not Likely",
};

const BADGE_CLASS = {
  likely_eligible: "badge-likely",
  needs_clarification: "badge-clarify",
  not_likely: "badge-not",
};

function formatTrait(key, value) {
  if (key === "needs_overseas" || key === "has_cultivable_land" || key === "shg_member") {
    return value ? "Yes" : "No";
  }
  if (key === "persona") return PERSONA_LABELS[value] || String(value);
  if (key === "gender") return String(value).charAt(0).toUpperCase() + String(value).slice(1);
  if (key === "annual_income" && typeof value === "number") {
    return `₹${value.toLocaleString("en-IN")}`;
  }
  if (key === "category") return String(value).toUpperCase();
  return String(value).replace(/_/g, " ");
}

function MatchCard({ match }) {
  const status = match.status || "";
  const rules = Array.isArray(match.matched_rules) ? match.matched_rules : [];
  const docs = Array.isArray(match.required_documents) ? match.required_documents : [];
  const steps = Array.isArray(match.application_steps) ? match.application_steps : [];
  const pitfalls = Array.isArray(match.rejection_pitfalls) ? match.rejection_pitfalls : [];
  const [saveState, setSaveState] = useState({ phase: "idle", message: "" });

  async function saveToTracker() {
    setSaveState({ phase: "saving", message: "" });
    try {
      await createTrackerItem({ slug: match.slug, reminder_date: null, checked_documents: [] });
      setSaveState({ phase: "saved", message: "Saved to your tracker" });
    } catch (e) {
      if (e.status === 409) {
        setSaveState({ phase: "exists", message: "Already in your tracker" });
      } else {
        setSaveState({ phase: "error", message: e.message });
      }
    }
  }

  return (
    <article className="match-card">
      <div className="match-head">
        <h3>{match.name}</h3>
        <span className={`match-badge ${BADGE_CLASS[status] || ""}`}>
          {BADGE_TEXT[status] || status}
        </span>
      </div>

      {match.amount_or_benefit && <p className="match-benefit">💰 {match.amount_or_benefit}</p>}

      {rules.length > 0 && (
        <ul className="rule-list">
          {rules.map((r, i) => (
            <li key={i}>
              <strong>{r.label}</strong>
              {r.reason && <span> — {r.reason}</span>}
            </li>
          ))}
        </ul>
      )}

      {docs.length > 0 && (
        <>
          <h4>Required documents</h4>
          <ul className="doc-list">
            {docs.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </>
      )}

      {steps.length > 0 && (
        <>
          <h4>How to apply</h4>
          <ol className="step-list">
            {steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </>
      )}

      {match.last_verified_date && (
        <p className="verified-note">Verified on {match.last_verified_date}</p>
      )}

      {pitfalls.length > 0 && (
        <details className="pitfalls">
          <summary>Common rejection pitfalls</summary>
          <ul>
            {pitfalls.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </details>
      )}

      {match.official_url && (
        <a className="official-link" href={match.official_url} target="_blank" rel="noopener noreferrer">
          Official portal ↗
        </a>
      )}

      <div className="save-track-row">
        <button
          type="button"
          className="save-track-btn"
          onClick={saveToTracker}
          disabled={saveState.phase === "saving"}
        >
          {saveState.phase === "saving" ? "Saving…" : "Save & Track"}
        </button>
        {saveState.message && (
          <p
            className={saveState.phase === "error" ? "save-track-msg error" : "save-track-msg"}
            role="status"
          >
            {saveState.message}
          </p>
        )}
      </div>
    </article>
  );
}

const CHAT_STORAGE_KEY = "civicledger_chat_v1";

// Persist the conversation for this browser tab so a refresh doesn't wipe it.
// sessionStorage (not localStorage): it clears when the tab closes.
function loadChatState() {
  try {
    const raw = sessionStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    if (s && Array.isArray(s.messages) && s.messages.length > 0) return s;
  } catch {
    // corrupted or unavailable storage — start fresh
  }
  return null;
}

export default function EligibilityChat() {
  const [saved] = useState(loadChatState);
  const [messages, setMessages] = useState(
    () => saved?.messages ?? [{ role: "assistant", content: WELCOME }]
  );
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState(() => saved?.profile ?? {});
  const [turnCount, setTurnCount] = useState(() => saved?.turnCount ?? 0);
  const [latest, setLatest] = useState(() => saved?.latest ?? null);
  const [forceResults, setForceResults] = useState(() => saved?.forceResults ?? false);
  const [personaChoice, setPersonaChoice] = useState("");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const threadEndRef = useRef(null);

  // Server-side history (per account) wins over the per-tab cache.
  useEffect(() => {
    let cancelled = false;
    fetchChatHistory()
      .then((h) => {
        if (cancelled || !h || !Array.isArray(h.messages) || h.messages.length === 0) return;
        setMessages([{ role: "assistant", content: WELCOME }, ...h.messages]);
        if (h.profile) setProfile(h.profile);
        if (typeof h.turn_count === "number") setTurnCount(h.turn_count);
      })
      .catch(() => {
        // offline/unauthorized — keep sessionStorage state
      })
      .finally(() => {
        if (!cancelled) setHistoryLoaded(true);
      });
    return () => { cancelled = true; };
  }, []);

  function resetChat() {
    setMessages([{ role: "assistant", content: WELCOME }]);
    setProfile({});
    setTurnCount(0);
    setLatest(null);
    setForceResults(false);
    try { sessionStorage.removeItem(CHAT_STORAGE_KEY); } catch {}
    clearChatHistory().catch(() => {});
  }

  useEffect(() => {
    try {
      sessionStorage.setItem(
        CHAT_STORAGE_KEY,
        JSON.stringify({ messages, profile, turnCount, latest, forceResults })
      );
    } catch {
      // storage full/unavailable — chat still works in-memory
    }
  }, [messages, profile, turnCount, latest, forceResults]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const traits = latest?.extracted_traits || {};
  const traitEntries = Object.keys(TRAIT_LABELS)
    .filter((key) => traits[key] !== null && traits[key] !== undefined && traits[key] !== "")
    .map((key) => [key, traits[key]]);

  const showResults =
    !latest?.is_answer &&
    (forceResults ||
      (latest !== null &&
        (latest.needs_more_info === false ||
          (latest.max_turns != null && latest.turn_count >= latest.max_turns))));

  const qaSources = latest?.is_answer && Array.isArray(latest?.context_snippets)
    ? [...new Set(latest.context_snippets.map((s) => s.name).filter(Boolean))]
    : [];

  async function send(text, { fromInput = false, showMatches = false } = {}) {
    const content = text.trim();
    if (!content || loading) return;

    // Send only a recent tail — the backend caps history length/content, and
    // older turns are already reflected in `profile` anyway.
    const history = messages
      .slice(-16)
      .map(({ role, content: c }) => ({ role, content: String(c).slice(0, 3900) }));
    setMessages((m) => [...m, { role: "user", content }]);
    if (fromInput) setInput("");
    setLoading(true);

    try {
      // An explicit persona selection overrides auto-detection.
      const effectiveProfile = personaChoice
        ? { ...profile, persona: personaChoice }
        : profile;
      const data = await postEligibilityChat({
        message: content,
        history,
        profile: effectiveProfile,
        turn_count: turnCount,
        show_matches_now: showMatches,
      });

      // Show the backend's reply verbatim — it already embeds follow-up
      // questions and matches the text stored in server-side history, so
      // later turns keep full conversational context.
      const reply =
        data.reply ||
        (data.is_answer
          ? "I couldn't answer that just now."
          : "Thanks, got it.");
      setMessages((m) => [...m, { role: "assistant", content: reply }]);

      if (data.profile) setProfile(data.profile);
      if (typeof data.turn_count === "number") setTurnCount(data.turn_count);
      setLatest(data);
      if (showMatches) setForceResults(true);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `Sorry, I couldn't check that just now (${e.message}). Your message is still in the box, so you can try again.`,
        },
      ]);
      if (fromInput) setInput(content);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    send(input, { fromInput: true });
  }

  return (
    <section id="ai" className="chat-panel">
      <div className="chat-container">
        <h2>AI Eligibility Check</h2>
        <p className="chat-intro">
          Tell us about your situation — students, farmers and women entrepreneurs
          are all supported. Results are indicative only.
        </p>
        <div className="persona-picker">
          <label htmlFor="chat-persona">I am a</label>
          <select
            id="chat-persona"
            value={personaChoice}
            onChange={(e) => setPersonaChoice(e.target.value)}
          >
            {PERSONA_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <p className="disclaimer">Indicative only, not a guarantee of eligibility. Confirm with the official portal.</p>
        <p className="privacy-note">Please don't share Aadhaar or other ID numbers.</p>

        {latest?.pii_warning && (
          <div className="pii-warning" role="alert">
            ⚠️ Sensitive ID numbers were removed from your message and were not stored.
          </div>
        )}

        <div className="sample-row">
          <span className="sample-label">Try a sample story:</span>
          {SAMPLE_STORIES.map((s) => (
            <button
              key={s.label}
              type="button"
              className="sample-btn"
              onClick={() => send(s.text)}
              disabled={loading}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="chat-thread" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role === "user" ? "bubble-user" : "bubble-assistant"}`}>
              {m.role === "assistant" ? <Markdown text={m.content} /> : m.content}
            </div>
          ))}
          {loading && <div className="bubble bubble-assistant bubble-typing">Thinking…</div>}
          <div ref={threadEndRef} />
        </div>

        {traitEntries.length > 0 && (
          <div className="trait-row" aria-label="Extracted details">
            {traitEntries.map(([key, value]) => (
              <span key={key} className="trait-chip">
                {TRAIT_LABELS[key]}: {formatTrait(key, value)}
              </span>
            ))}
          </div>
        )}

        {qaSources.length > 0 && (
          <p className="qa-sources">
            Answered from: {qaSources.join(", ")}
          </p>
        )}

        <form className="chat-form" onSubmit={handleSubmit}>
          <input
            type="text"
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe your situation…"
            aria-label="Your message"
            disabled={loading}
          />
          <button type="submit" className="send-btn" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>

        <button
          type="button"
          className="matches-btn"
          onClick={() => send("Show best matches now", { showMatches: true })}
          disabled={loading}
        >
          Show best matches now
        </button>

        {historyLoaded && messages.length > 1 && (
          <button type="button" className="clear-chat-btn" onClick={resetChat}>
            Clear conversation
          </button>
        )}

        {showResults && (
          <div className="results">
            <h3>Your best matches</h3>
            {Array.isArray(latest?.matches) && latest.matches.length > 0 ? (
              latest.matches.map((m, i) => <MatchCard key={m.slug || m.name || i} match={m} />)
            ) : (
              <p className="status">No matches yet. Try adding more details about your situation.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
