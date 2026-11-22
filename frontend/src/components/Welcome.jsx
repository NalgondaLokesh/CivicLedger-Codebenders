import "./Welcome.css";

const ACTIONS = [
  {
    id: "ai",
    icon: "✨",
    title: "Check your eligibility",
    text: "Answer a few questions and see which schemes you likely qualify for.",
  },
  {
    id: "explore",
    icon: "📚",
    title: "Explore schemes",
    text: "Browse all verified Telangana schemes with official links and rules.",
  },
  {
    id: "tracker",
    icon: "📋",
    title: "My tracker",
    text: "Track applications, tick off documents and set reminders.",
  },
];

export default function Welcome({ name, onNavigate }) {
  return (
    <div className="welcome">
      <section className="card welcome-card">
        <p className="eyebrow">You're all set</p>
        <h1>Welcome{ name ? `, ${name}` : ""}!</h1>
        <p className="welcome-lead">
          Your account is ready. Pick where you'd like to start — everything is
          private to you and indicative only.
        </p>
        <div className="welcome-actions">
          {ACTIONS.map((a) => (
            <button
              type="button"
              key={a.id}
              className="card welcome-action"
              onClick={() => onNavigate(a.id)}
            >
              <span className="welcome-icon" aria-hidden>{a.icon}</span>
              <span className="welcome-action-text">
                <strong>{a.title}</strong>
                <span>{a.text}</span>
              </span>
              <span className="welcome-arrow" aria-hidden>→</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
