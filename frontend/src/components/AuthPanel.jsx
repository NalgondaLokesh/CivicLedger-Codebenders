import { useState } from "react";
import { signin, signup } from "../api";
import "./AuthPanel.css";

export const SESSION_KEY = "civicledger_session";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Sessions are server-issued bearer tokens (see /api/auth). Only the token
// and basic profile are stored in localStorage on this device.

export function readSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed.token === "string" &&
      parsed.user &&
      typeof parsed.user.email === "string"
    ) {
      return {
        token: parsed.token,
        user: {
          id: String(parsed.user.id || ""),
          email: parsed.user.email,
          displayName:
            typeof parsed.user.displayName === "string"
              ? parsed.user.displayName
              : parsed.user.email.split("@")[0],
        },
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function writeSession(session) {
  try {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        token: session.token,
        user: {
          id: session.user.id,
          email: session.user.email,
          displayName: session.user.displayName,
        },
      })
    );
  } catch {
    // Storage unavailable (private mode, quota): session lasts for this page only.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}

function toSession(auth) {
  return {
    token: auth.token,
    user: {
      id: auth.user.id,
      email: auth.user.email,
      displayName: auth.user.display_name || auth.user.email.split("@")[0],
    },
  };
}

export default function AuthPanel({ session, onSessionChange, onExplore }) {
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const switchMode = (next) => {
    setMode(next);
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();
    if (!EMAIL_RE.test(trimmedEmail)) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const auth =
        mode === "signup"
          ? await signup({ email: trimmedEmail, password, displayName: displayName.trim() })
          : await signin({ email: trimmedEmail, password });
      onSessionChange(toSession(auth));
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (session) {
    return (
      <section className="auth-wrap" aria-labelledby="auth-heading">
        <div className="card auth-card">
          <p className="eyebrow">Your account</p>
          <h1 id="auth-heading">Signed in as {session.user.displayName}</h1>
          <p className="auth-note">{session.user.email}</p>
          <div className="auth-actions">
            <button type="button" className="btn-primary" onClick={onExplore}>
              Go to Scheme Explorer
            </button>
            <button type="button" className="btn-secondary" onClick={() => onSessionChange(null)}>
              Sign out
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="auth-wrap" aria-labelledby="auth-heading">
      <div className="card auth-card">
        <p className="eyebrow">Welcome to CivicLedger</p>
        <h1 id="auth-heading">{mode === "signup" ? "Create your account" : "Sign in to continue"}</h1>
        <p className="auth-note">
          One account keeps your application tracker private to you. We never ask
          for government ID numbers.
        </p>

        <div className="auth-toggle" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            className={mode === "signin" ? "active" : ""}
            onClick={() => switchMode("signin")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            className={mode === "signup" ? "active" : ""}
            onClick={() => switchMode("signup")}
          >
            Sign up
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {mode === "signup" && (
            <label className="auth-field">
              <span>Display name (optional)</span>
              <input
                type="text"
                autoComplete="name"
                maxLength={60}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="e.g. Amara"
              />
            </label>
          )}
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              maxLength={200}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
              required
            />
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <p className="auth-privacy">
            We never ask for or store government ID numbers. Your password is
            hashed; sessions use secure tokens stored on this device.
          </p>

          <div className="auth-actions">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
