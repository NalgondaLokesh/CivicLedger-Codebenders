import { useEffect, useState } from "react";
import {
  fetchAdminSchemes,
  upsertAdminScheme,
  getAdminKey,
  setAdminKey,
} from "../api";
import "./AdminPanel.css";

const PERSONA_OPTIONS = [
  { value: "telangana_students", label: "Students" },
  { value: "telangana_farmers", label: "Small Farmers" },
  { value: "telangana_women_entrepreneurs", label: "Women Entrepreneurs" },
];

const LEVEL_OPTIONS = [
  { value: "", label: "—" },
  { value: "post_matric", label: "Post-Matric" },
  { value: "professional", label: "Professional" },
  { value: "overseas", label: "Overseas" },
];

const SCHEME_LEVEL_OPTIONS = [
  { value: "state", label: "State (Telangana)" },
  { value: "central", label: "Central (Govt. of India)" },
];

const CATEGORY_OPTIONS = [
  { value: "all", label: "All" },
  { value: "sc", label: "SC" },
  { value: "st", label: "ST" },
  { value: "bc", label: "BC" },
  { value: "ebc", label: "EBC" },
  { value: "minority", label: "Minority" },
  { value: "general", label: "General" },
];

const RULE_TYPES = ["income_limit", "institution_type", "attendance", "merit", "residency", "other"];
const GENDER_OPTIONS = [
  { value: "", label: "—" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
];

const NEW_SLUG = "__new__";
const today = () => new Date().toISOString().slice(0, 10);

const lines = (s) =>
  String(s || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);

const blankForm = () => ({
  slug: "",
  name: "",
  summary: "",
  scheme_level: "state",
  persona: "telangana_students",
  education_level: "",
  category: "all",
  categories: "",
  rules: [{ type: "other", label: "", value: "" }],
  required_documents: "",
  application_steps: "",
  rejection_pitfalls: "",
  official_url: "",
  last_verified_date: today(),
  max_income_limit: "",
  amount_or_benefit: "",
  min_age: "",
  max_age: "",
  gender: "",
  requires_shg_membership: false,
  requires_cultivable_land: false,
  active: true,
});

function schemeToForm(s) {
  return {
    slug: s.slug || "",
    name: s.name || "",
    summary: s.summary || "",
    scheme_level: s.scheme_level || "state",
    persona: s.persona || s.target_group || "telangana_students",
    education_level: s.education_level || "",
    category: s.category || "all",
    categories: (s.categories || []).join(", "),
    rules:
      s.rules && s.rules.length
        ? s.rules.map((r) => ({
            type: r.type || "other",
            label: r.label || "",
            value: String(r.value ?? ""),
          }))
        : [{ type: "other", label: "", value: "" }],
    required_documents: (s.required_documents || []).join("\n"),
    application_steps: (s.application_steps || []).join("\n"),
    rejection_pitfalls: (s.rejection_pitfalls || []).join("\n"),
    official_url: s.official_url || "",
    last_verified_date: String(s.last_verified_date || "").slice(0, 10) || today(),
    max_income_limit: s.max_income_limit ?? "",
    amount_or_benefit: s.amount_or_benefit || "",
    min_age: s.min_age ?? "",
    max_age: s.max_age ?? "",
    gender: s.gender || "",
    requires_shg_membership: !!s.requires_shg_membership,
    requires_cultivable_land: !!s.requires_cultivable_land,
    active: s.active !== false,
  };
}

function buildPayload(f) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    slug: f.slug.trim(),
    name: f.name.trim(),
    summary: f.summary.trim(),
    scheme_level: f.scheme_level || "state",
    persona: f.persona,
    target_group: f.persona,
    education_level: f.education_level || null,
    category: f.category || "all",
    categories: f.categories
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean),
    rules: f.rules
      .filter((r) => r.label.trim() || r.value.trim())
      .map((r) => ({
        type: r.type || "other",
        label: r.label.trim(),
        value: r.value.trim(),
      })),
    required_documents: lines(f.required_documents),
    application_steps: lines(f.application_steps),
    rejection_pitfalls: lines(f.rejection_pitfalls),
    official_url: f.official_url.trim(),
    last_verified_date: f.last_verified_date,
    max_income_limit: num(f.max_income_limit),
    max_annual_income_inr: null,
    amount_or_benefit: f.amount_or_benefit.trim() || null,
    min_age: num(f.min_age),
    max_age: num(f.max_age),
    gender: f.gender || null,
    requires_shg_membership: !!f.requires_shg_membership,
    requires_cultivable_land: !!f.requires_cultivable_land,
    active: !!f.active,
  };
}

export default function AdminPanel({ onClose, onSaved }) {
  const [keyDraft, setKeyDraft] = useState("");
  const [adminKey, setAdminKeyState] = useState("");
  const [verified, setVerified] = useState(false);
  const [schemes, setSchemes] = useState([]);
  const [selected, setSelected] = useState(NEW_SLUG);
  const [form, setForm] = useState(blankForm);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Returns true only when the server accepts the key (200 from /api/admin).
  const loadSchemes = async (key) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminSchemes(key);
      const items = data.items || [];
      setSchemes(items);
      setSelected((prev) =>
        prev === NEW_SLUG || items.some((s) => s.slug === prev) ? prev : NEW_SLUG
      );
      return true;
    } catch (e) {
      setError(e.message);
      setSchemes([]);
      return false;
    } finally {
      setLoading(false);
    }
  };

  // On open: if a key is stored, verify it before showing anything.
  useEffect(() => {
    const stored = getAdminKey();
    if (!stored) return;
    loadSchemes(stored).then((ok) => {
      if (ok) {
        setAdminKeyState(stored);
        setVerified(true);
      } else {
        setAdminKey(""); // stored key was rejected — make the user re-enter it
        setError("Stored admin key was rejected. Enter a valid ADMIN_API_KEY.");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveKey = async () => {
    const k = keyDraft.trim();
    if (!k) return;
    setKeyDraft("");
    setResult(null);
    const ok = await loadSchemes(k);
    if (ok) {
      setAdminKey(k);
      setAdminKeyState(k);
      setVerified(true);
    }
  };

  const clearKey = () => {
    setAdminKey("");
    setAdminKeyState("");
    setVerified(false);
    setSchemes([]);
    setSelected(NEW_SLUG);
    setForm(blankForm());
    setResult(null);
    setError(null);
  };

  const onSelect = (slug) => {
    setSelected(slug);
    setResult(null);
    setError(null);
    if (slug === NEW_SLUG) {
      setForm(blankForm());
    } else {
      const s = schemes.find((x) => x.slug === slug);
      if (s) setForm(schemeToForm(s));
    }
  };

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setRule = (i, patch) =>
    setForm((f) => ({
      ...f,
      rules: f.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)),
    }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    const payload = buildPayload(form);
    const missing = [
      ["slug", "Slug"],
      ["name", "Name"],
      ["summary", "Summary"],
      ["official_url", "Official URL"],
      ["last_verified_date", "Last verified date"],
    ].filter(([k]) => !payload[k]);
    if (missing.length) {
      setError(`Required: ${missing.map(([, label]) => label).join(", ")}`);
      return;
    }
    setBusy(true);
    try {
      const data = await upsertAdminScheme(payload, adminKey);
      setResult(data);
      // Reflect the saved doc in the picker without a full reload.
      setSchemes((prev) => {
        const rest = prev.filter((s) => s.slug !== data.scheme.slug);
        return [...rest, data.scheme].sort((a, b) =>
          String(a.name || "").localeCompare(String(b.name || ""))
        );
      });
      setSelected(data.scheme.slug);
      onSaved && onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-overlay" role="presentation" onClick={onClose}>
      <aside
        className="admin-drawer"
        role="dialog"
        aria-label="Admin scheme editor"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="admin-head">
          <div>
            <h2>Admin · Scheme Sync</h2>
            <p className="muted">
              Upsert schemes to MongoDB and sync Qdrant Cloud. Indicative only —
              always verify on the official portal.
            </p>
          </div>
          <button type="button" className="admin-close" onClick={onClose} aria-label="Close admin panel">
            ×
          </button>
        </header>

        <section className="admin-key-row">
          <input
            type="password"
            className="admin-input"
            placeholder="ADMIN_API_KEY"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            autoComplete="off"
          />
          <button type="button" className="admin-btn" onClick={saveKey} disabled={!keyDraft.trim() || loading}>
            Set key
          </button>
          {verified && (
            <button type="button" className="admin-btn ghost" onClick={clearKey}>
              Clear
            </button>
          )}
        </section>

        {!verified ? (
          <>
            <p className="status">
              {loading
                ? "Verifying admin key…"
                : "Enter a valid ADMIN_API_KEY to load and edit schemes."}
            </p>
            {error && <p className="status error">⚠️ {error}</p>}
          </>
        ) : (
          <form className="admin-form" onSubmit={submit}>
            <div className="admin-row">
              <label className="admin-field">
                <span>Scheme</span>
                <select
                  className="admin-input"
                  value={selected}
                  onChange={(e) => onSelect(e.target.value)}
                  disabled={loading}
                >
                  <option value={NEW_SLUG}>+ New scheme…</option>
                  {schemes.map((s) => (
                    <option key={s.slug} value={s.slug}>
                      {s.name} ({s.slug})
                    </option>
                  ))}
                </select>
              </label>
              <label className="admin-field">
                <span>Slug</span>
                <input
                  className="admin-input"
                  value={form.slug}
                  onChange={(e) => set({ slug: e.target.value })}
                  placeholder="epass-post-matric-sc"
                  required
                />
              </label>
            </div>

            <label className="admin-field">
              <span>Name</span>
              <input className="admin-input" value={form.name} onChange={(e) => set({ name: e.target.value })} required />
            </label>
            <label className="admin-field">
              <span>Summary</span>
              <textarea className="admin-input" rows={2} value={form.summary} onChange={(e) => set({ summary: e.target.value })} required />
            </label>

            <div className="admin-row admin-row-3">
              <label className="admin-field">
                <span>Scheme level</span>
                <select className="admin-input" value={form.scheme_level} onChange={(e) => set({ scheme_level: e.target.value })}>
                  {SCHEME_LEVEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Persona</span>
                <select className="admin-input" value={form.persona} onChange={(e) => set({ persona: e.target.value })}>
                  {PERSONA_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Education level</span>
                <select className="admin-input" value={form.education_level} onChange={(e) => set({ education_level: e.target.value })}>
                  {LEVEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Category</span>
                <select className="admin-input" value={form.category} onChange={(e) => set({ category: e.target.value })}>
                  {CATEGORY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
            </div>

            <div className="admin-row">
              <label className="admin-field">
                <span>Eligible categories (comma-separated, optional)</span>
                <input className="admin-input" value={form.categories} onChange={(e) => set({ categories: e.target.value })} placeholder="sc, st" />
              </label>
              <label className="admin-field">
                <span>Max income limit (INR/year, blank = no cap)</span>
                <input className="admin-input" type="number" min="0" value={form.max_income_limit} onChange={(e) => set({ max_income_limit: e.target.value })} />
              </label>
            </div>

            <div className="admin-row">
              <label className="admin-field">
                <span>Amount / benefit</span>
                <input className="admin-input" value={form.amount_or_benefit} onChange={(e) => set({ amount_or_benefit: e.target.value })} />
              </label>
              <label className="admin-field">
                <span>Gender requirement (optional)</span>
                <select className="admin-input" value={form.gender} onChange={(e) => set({ gender: e.target.value })}>
                  {GENDER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="admin-field">
                <span>Age range (optional)</span>
                <span className="admin-inline">
                  <input className="admin-input" type="number" min="0" placeholder="min" value={form.min_age} onChange={(e) => set({ min_age: e.target.value })} />
                  <input className="admin-input" type="number" min="0" placeholder="max" value={form.max_age} onChange={(e) => set({ max_age: e.target.value })} />
                </span>
              </label>
            </div>

            <fieldset className="admin-fieldset">
              <legend>Rules</legend>
              {form.rules.map((r, i) => (
                <div className="admin-rule" key={i}>
                  <select
                    className="admin-input"
                    value={r.type}
                    onChange={(e) => setRule(i, { type: e.target.value })}
                    aria-label="Rule type"
                  >
                    {RULE_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
                  </select>
                  <input
                    className="admin-input"
                    placeholder="Label"
                    value={r.label}
                    onChange={(e) => setRule(i, { label: e.target.value })}
                  />
                  <input
                    className="admin-input"
                    placeholder="Value"
                    value={r.value}
                    onChange={(e) => setRule(i, { value: e.target.value })}
                  />
                  <button
                    type="button"
                    className="admin-btn ghost small"
                    onClick={() => setForm((f) => ({ ...f, rules: f.rules.filter((_, j) => j !== i) }))}
                    disabled={form.rules.length <= 1}
                    aria-label="Remove rule"
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="admin-btn ghost small"
                onClick={() => setForm((f) => ({ ...f, rules: [...f.rules, { type: "other", label: "", value: "" }] }))}
              >
                + Add rule
              </button>
            </fieldset>

            <label className="admin-field">
              <span>Required documents (one per line)</span>
              <textarea className="admin-input" rows={4} value={form.required_documents} onChange={(e) => set({ required_documents: e.target.value })} />
            </label>
            <label className="admin-field">
              <span>Application steps (one per line)</span>
              <textarea className="admin-input" rows={4} value={form.application_steps} onChange={(e) => set({ application_steps: e.target.value })} />
            </label>
            <label className="admin-field">
              <span>Rejection pitfalls (one per line, optional)</span>
              <textarea className="admin-input" rows={3} value={form.rejection_pitfalls} onChange={(e) => set({ rejection_pitfalls: e.target.value })} />
            </label>

            <div className="admin-row admin-row-2">
              <label className="admin-field">
                <span>Official URL</span>
                <input className="admin-input" type="url" value={form.official_url} onChange={(e) => set({ official_url: e.target.value })} required placeholder="https://…" />
              </label>
              <label className="admin-field">
                <span>Last verified date</span>
                <input className="admin-input" type="date" value={form.last_verified_date} onChange={(e) => set({ last_verified_date: e.target.value })} required />
              </label>
            </div>

            <div className="admin-checks">
              <label className="admin-check">
                <input type="checkbox" checked={form.requires_shg_membership} onChange={(e) => set({ requires_shg_membership: e.target.checked })} />
                Requires SHG membership
              </label>
              <label className="admin-check">
                <input type="checkbox" checked={form.requires_cultivable_land} onChange={(e) => set({ requires_cultivable_land: e.target.checked })} />
                Requires cultivable land
              </label>
              <label className="admin-check">
                <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} />
                Active (uncheck to remove from index)
              </label>
            </div>

            {error && <p className="status error">⚠️ {error}</p>}
            {loading && <p className="status">Loading schemes…</p>}

            {result && (
              <div className={`admin-result ${result.qdrant?.status}`}>
                <strong>
                  {result.qdrant?.status === "synced"
                    ? "✓ Saved to MongoDB — Qdrant synced"
                    : result.qdrant?.status === "skipped_unconfigured"
                      ? "✓ Saved to MongoDB — Qdrant not configured"
                      : result.qdrant?.status === "failed"
                        ? "✓ Saved to MongoDB — Qdrant sync failed"
                        : "✓ Saved to MongoDB"}
                </strong>
                <span className="muted">
                  {result.qdrant?.message}
                  {result.qdrant?.chunks != null && ` · ${result.qdrant.chunks} chunk(s)`}
                </span>
              </div>
            )}

            <div className="admin-actions">
              <button type="submit" className="admin-btn primary" disabled={busy || !adminKey}>
                {busy ? "Saving…" : "Save & sync Qdrant"}
              </button>
              <button type="button" className="admin-btn ghost" onClick={() => loadSchemes(adminKey)} disabled={loading}>
                Reload list
              </button>
            </div>
          </form>
        )}
      </aside>
    </div>
  );
}
