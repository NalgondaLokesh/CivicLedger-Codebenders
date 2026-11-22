const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function fetchSchemes({ educationLevel, category, persona, schemeLevel, maxIncome } = {}) {
  const params = new URLSearchParams();
  if (educationLevel) params.set("education_level", educationLevel);
  if (category) params.set("category", category);
  if (persona) params.set("persona", persona);
  if (schemeLevel) params.set("scheme_level", schemeLevel);
  if (maxIncome) params.set("max_income", maxIncome);

  const res = await fetch(`${API_BASE}/api/schemes?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to load schemes (${res.status})`);
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function postEligibilityChat(payload) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/eligibility/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Eligibility check failed (${res.status})`);
  }
  return data;
}

// ------------------------------------------------------------- auth
// Sessions are opaque bearer tokens issued by /api/auth. Stored in
// localStorage; never sent anywhere except as an Authorization header.

export function getToken() {
  try {
    const s = JSON.parse(localStorage.getItem("civicledger_session") || "null");
    return s && typeof s.token === "string" ? s.token : null;
  } catch {
    return null;
  }
}

async function authRequest(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

export async function signup({ email, password, displayName }) {
  return authRequest("/api/auth/signup", {
    email,
    password,
    display_name: displayName || undefined,
  });
}

export async function signin({ email, password }) {
  return authRequest("/api/auth/signin", { email, password });
}

export async function fetchMe() {
  const token = getToken();
  if (!token) return null;
  let res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401 && (await refreshSession())) {
    const newToken = getToken();
    res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${newToken}` },
    });
  }
  if (!res.ok) return null;
  return res.json();
}

export async function logout() {
  const token = getToken();
  try {
    if (token) {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  } catch {
    // Network failure — clear locally anyway.
  }
}

// Swap an expired token for a fresh one; returns true on success.
export async function refreshSession() {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return false;
    const data = await res.json();
    try {
      const raw = localStorage.getItem("civicledger_session");
      const s = raw ? JSON.parse(raw) : {};
      s.token = data.token;
      if (data.user) {
        s.user = {
          id: data.user.id,
          email: data.user.email,
          displayName: data.user.display_name || data.user.email.split("@")[0],
        };
      }
      localStorage.setItem("civicledger_session", JSON.stringify(s));
    } catch {
      // storage unavailable — in-memory token still works this page
    }
    return true;
  } catch {
    return false;
  }
}

export async function fetchChatHistory() {
  return trackerRequest("/api/eligibility/history", { fallback: "Failed to load chat history" });
}

export async function clearChatHistory() {
  return trackerRequest("/api/eligibility/history", { method: "DELETE", fallback: "Failed to clear chat history" });
}

// ------------------------------------------------------------- tracker
// Shared request helper for the Application Tracker endpoints.
// Errors carry the server `detail` message and the HTTP `status`.
async function trackerRequest(path, { method = "GET", body, fallback = "Request failed", retried = false } = {}) {
  const token = getToken();
  const init = {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    // Expired token? Refresh once and retry.
    if (res.status === 401 && token && !retried && (await refreshSession())) {
      return trackerRequest(path, { method, body, fallback, retried: true });
    }
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    const error = new Error(detail || `${fallback} (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return data;
}

export async function fetchTracker(status) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const query = params.toString();
  return trackerRequest(`/api/tracker${query ? `?${query}` : ""}`, {
    fallback: "Failed to load tracker",
  });
}

export async function createTrackerItem(payload) {
  return trackerRequest("/api/tracker", {
    method: "POST",
    body: payload,
    fallback: "Could not save to tracker",
  });
}

export async function updateTrackerItem(id, patch) {
  return trackerRequest(`/api/tracker/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: patch,
    fallback: "Could not update tracker item",
  });
}

export async function deleteTrackerItem(id) {
  return trackerRequest(`/api/tracker/${encodeURIComponent(id)}`, {
    method: "DELETE",
    fallback: "Could not remove tracker item",
  });
}

export async function fetchChecklist() {
  return trackerRequest("/api/tracker/checklist", {
    fallback: "Failed to load checklist",
  });
}

export async function toggleChecklistDocument(document, checked) {
  return trackerRequest("/api/tracker/checklist/toggle", {
    method: "POST",
    body: { document, checked },
    fallback: "Could not update checklist",
  });
}

// ------------------------------------------------------------- attachments
// Real file upload/download. Bytes are stored server-side per account.

export async function uploadTrackerFile(itemId, file) {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/tracker/${encodeURIComponent(itemId)}/attachments`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    if (res.status === 401 && token && (await refreshSession())) {
      return uploadTrackerFile(itemId, file);
    }
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Upload failed (${res.status})`);
  }
  return data;
}

export async function downloadTrackerFile(fileId, filename) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/tracker/files/${encodeURIComponent(fileId)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document";
  a.click();
  URL.revokeObjectURL(url);
}

// ------------------------------------------------------------- admin
// Scheme upsert is guarded by ADMIN_API_KEY (X-Admin-Key header). The key is
// kept in localStorage on this device only, like the session token.

const ADMIN_KEY_STORAGE = "civicledger_admin_key";

export function getAdminKey() {
  try {
    return localStorage.getItem(ADMIN_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setAdminKey(key) {
  try {
    if (key) localStorage.setItem(ADMIN_KEY_STORAGE, key);
    else localStorage.removeItem(ADMIN_KEY_STORAGE);
  } catch {
    // storage unavailable — key lasts for this page only
  }
}

async function adminRequest(path, { method = "GET", body, adminKey } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "X-Admin-Key": adminKey || "",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail =
      data && typeof data.detail === "string"
        ? data.detail
        : data && data.detail
          ? JSON.stringify(data.detail)
          : null;
    const error = new Error(detail || `Admin request failed (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return data;
}

export function fetchAdminSchemes(adminKey) {
  return adminRequest("/api/admin/schemes", { adminKey });
}

export function upsertAdminScheme(payload, adminKey) {
  return adminRequest("/api/admin/schemes", {
    method: "POST",
    body: payload,
    adminKey,
  });
}

export async function deleteTrackerFile(fileId) {
  return trackerRequest(`/api/tracker/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    fallback: "Could not remove file",
  });
}
