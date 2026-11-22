import { useEffect, useRef, useState } from "react";
import {
  fetchTracker,
  fetchChecklist,
  updateTrackerItem,
  deleteTrackerItem,
  toggleChecklistDocument,
  uploadTrackerFile,
  downloadTrackerFile,
  deleteTrackerFile,
} from "../api.js";
import "./ApplicationTracker.css";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "documents_pending", label: "Documents Pending" },
  { value: "ready_to_apply", label: "Ready to Apply" },
  { value: "applied", label: "Applied" },
  { value: "follow_up", label: "Follow Up" },
];

const STATUS_OPTIONS = STATUS_FILTERS.filter((f) => f.value !== "");

const REMINDER_BADGES = {
  overdue: { text: "Overdue", className: "reminder-overdue" },
  due_soon: { text: "Due soon", className: "reminder-soon" },
  scheduled: { text: "Scheduled", className: "reminder-scheduled" },
};

const NOTES_MAX = 500;

// Backend stores checked_documents as normalized keys; required_documents keep
// original casing. Normalize both sides before comparing.
const normDoc = (s) => s.trim().toLowerCase().replace(/\s+/g, " ");

function TrackerCard({ item, onUpdate, onRemove, onRefresh }) {
  const [notesDraft, setNotesDraft] = useState(item.notes || "");
  const [confirming, setConfirming] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileRef = useRef(null);

  const checkedDocs = Array.isArray(item.checked_documents) ? item.checked_documents : [];
  const requiredDocs = Array.isArray(item.required_documents) ? item.required_documents : [];
  const attachments = Array.isArray(item.attachments) ? item.attachments : [];
  const reminder = REMINDER_BADGES[item.reminder_state] || null;

  useEffect(() => {
    setNotesDraft(item.notes || "");
  }, [item.notes]);

  function saveNotes() {
    if (notesDraft === (item.notes || "")) return;
    onUpdate(item.id, { notes: notesDraft });
  }

  // Uploads file bytes to the server (owner-only, max 5 MB).
  async function handleFiles(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length || uploading) return;
    setUploading(true);
    setUploadError("");
    try {
      for (const f of files.slice(0, 20 - attachments.length)) {
        await uploadTrackerFile(item.id, f);
      }
      onRefresh();
    } catch (err) {
      setUploadError(err.message || "Upload failed");
      onRefresh();
    } finally {
      setUploading(false);
    }
  }

  async function removeAttachment(a) {
    try {
      if (a.file_id) {
        await deleteTrackerFile(a.file_id);
      } else {
        // Legacy metadata-only entry: drop it via PATCH.
        onUpdate(item.id, { attachments: attachments.filter((x) => x.name !== a.name) });
        return;
      }
      onRefresh();
    } catch (err) {
      setUploadError(err.message || "Could not remove file");
    }
  }

  function downloadAttachment(a) {
    if (!a.file_id) return;
    downloadTrackerFile(a.file_id, a.name).catch((err) =>
      setUploadError(err.message || "Download failed")
    );
  }

  function toggleDocument(doc) {
    const key = normDoc(doc);
    const next = checkedDocs.some((d) => normDoc(d) === key)
      ? checkedDocs.filter((d) => normDoc(d) !== key)
      : [...checkedDocs, key];
    onUpdate(item.id, { checked_documents: next });
  }

  return (
    <article className="tracker-card">
      <div className="tracker-card-head">
        <h3>{item.name}</h3>
        {reminder && (
          <span className={`reminder-badge ${reminder.className}`}>{reminder.text}</span>
        )}
      </div>

      <p className="verified-badge">Verified on {item.last_verified_date}</p>

      <div className="status-group" role="group" aria-label={`Status for ${item.name}`}>
        {STATUS_OPTIONS.map((s) => {
          const active = item.status === s.value;
          return (
            <button
              key={s.value}
              type="button"
              className={active ? "status-btn active" : "status-btn"}
              aria-pressed={active}
              onClick={() => onUpdate(item.id, { status: s.value })}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <label className="field">
        <span>Reminder date</span>
        <input
          type="date"
          value={item.reminder_date || ""}
          onChange={(e) => onUpdate(item.id, { reminder_date: e.target.value || null })}
        />
      </label>

      {requiredDocs.length > 0 && (
        <fieldset className="doc-fieldset">
          <legend>Documents</legend>
          {requiredDocs.map((doc) => (
            <label key={doc} className="check-row">
              <input
                type="checkbox"
                checked={checkedDocs.some((d) => normDoc(d) === normDoc(doc))}
                onChange={() => toggleDocument(doc)}
              />
              <span>{doc}</span>
            </label>
          ))}
        </fieldset>
      )}

      {attachments.length > 0 && (
        <div className="attach-list" aria-label="Attached documents">
          {attachments.map((a) => (
            <span key={a.file_id || a.name} className="attach-chip" title={`${a.name} (${a.size} bytes)`}>
              {a.file_id ? (
                <button
                  type="button"
                  className="attach-download"
                  onClick={() => downloadAttachment(a)}
                  title="Download file"
                >
                  📎 {a.name}
                </button>
              ) : (
                <span>📎 {a.name}</span>
              )}
              <button
                type="button"
                className="attach-remove"
                aria-label={`Remove ${a.name}`}
                onClick={() => removeAttachment(a)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {uploadError && <p className="attach-error" role="alert">{uploadError}</p>}

      <div className="attach-row">
        <input
          ref={fileRef}
          type="file"
          multiple
          className="visually-hidden"
          accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx"
          onChange={handleFiles}
          aria-hidden="true"
          tabIndex={-1}
        />
        <button
          type="button"
          className="ghost-btn"
          onClick={() => fileRef.current?.click()}
          disabled={uploading || attachments.length >= 20}
        >
          {uploading ? "Uploading…" : "📎 Attach proof (max 5 MB)"}
        </button>
      </div>

      <label className="field">
        <span>Notes</span>
        <textarea
          rows={2}
          maxLength={NOTES_MAX}
          value={notesDraft}
          onChange={(e) => setNotesDraft(e.target.value)}
          onBlur={saveNotes}
        />
        <small className="field-hint">{notesDraft.length}/{NOTES_MAX}</small>
      </label>

      <div className="tracker-card-foot">
        <a className="official-link" href={item.official_url} target="_blank" rel="noopener noreferrer">
          Official site ↗
        </a>
        {confirming ? (
          <div className="confirm-row">
            <span>Remove this scheme?</span>
            <button type="button" className="danger-btn" onClick={() => onRemove(item.id)}>
              Yes, remove
            </button>
            <button type="button" className="ghost-btn" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className="ghost-btn" onClick={() => setConfirming(true)}>
            Remove
          </button>
        )}
      </div>
    </article>
  );
}

export default function ApplicationTracker({ onGoToChat }) {
  const [filter, setFilter] = useState("");
  const [version, setVersion] = useState(0);
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [itemsError, setItemsError] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [checklistError, setChecklistError] = useState(null);
  const [actionError, setActionError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setItemsLoading(true);
    fetchTracker(filter || undefined)
      .then((data) => {
        if (cancelled) return;
        setItems(Array.isArray(data.items) ? data.items : []);
        setItemsError(null);
      })
      .catch((e) => {
        if (!cancelled) setItemsError(e.message);
      })
      .finally(() => {
        if (!cancelled) setItemsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filter, version]);

  useEffect(() => {
    let cancelled = false;
    fetchChecklist()
      .then((data) => {
        if (cancelled) return;
        setChecklist(data);
        setChecklistError(null);
      })
      .catch((e) => {
        if (!cancelled) setChecklistError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  function refresh() {
    setVersion((v) => v + 1);
  }

  async function runAction(action) {
    setActionError(null);
    try {
      await action();
    } catch (e) {
      setActionError(e.message);
    } finally {
      refresh();
    }
  }

  function handleUpdate(id, patch) {
    return runAction(() => updateTrackerItem(id, patch));
  }

  function handleRemove(id) {
    return runAction(() => deleteTrackerItem(id));
  }

  function handleToggleDocument(name, checked) {
    return runAction(async () => {
      const next = await toggleChecklistDocument(name, checked);
      setChecklist(next);
    });
  }

  const docs = Array.isArray(checklist?.documents) ? checklist.documents : [];
  const checkedCount = checklist?.checked_count ?? 0;
  const totalCount = checklist?.total_count ?? 0;
  const progress = Math.max(0, Math.min(100, checklist?.progress_percent ?? 0));

  return (
    <section id="tracker" className="tracker-panel">
      <div className="tracker-container">
        <div className="tracker-banner" role="note">
          <p className="disclaimer">
            Indicative only, not a guarantee of eligibility. Confirm with the official portal.
          </p>
          <p className="privacy-note">Don't share Aadhaar, PAN or other ID numbers here.</p>
        </div>

        <h2>Application Tracker</h2>
        <p className="chat-intro">
          Keep track of the schemes you've saved, the documents you need and where each application stands.
        </p>

        <div className="filter-pills" role="group" aria-label="Filter tracked schemes by status">
          {STATUS_FILTERS.map((f) => {
            const active = filter === f.value;
            return (
              <button
                key={f.value || "all"}
                type="button"
                className={active ? "pill active" : "pill"}
                aria-pressed={active}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            );
          })}
        </div>

        {actionError && <p className="tracker-error" role="alert">⚠️ {actionError}</p>}

        <section className="checklist-block" aria-labelledby="tracker-checklist-heading">
          <h3 id="tracker-checklist-heading">Document checklist</h3>
          {checklistError && <p className="tracker-error" role="alert">⚠️ {checklistError}</p>}
          {!checklist && !checklistError && <p className="status">Loading checklist…</p>}
          {checklist && (
            <>
              <div className="progress-wrap">
                <div
                  className="progress-track"
                  role="progressbar"
                  aria-label="Documents ready"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={progress}
                >
                  <div className="progress-fill" style={{ width: `${progress}%` }} />
                </div>
                <p className="progress-text">
                  {checkedCount} of {totalCount} documents ready
                </p>
              </div>

              {docs.length === 0 ? (
                <div className="status">
                  <p>Save a scheme from the AI Check to build your document checklist.</p>
                  {onGoToChat && (
                    <button type="button" className="btn-primary tracker-cta" onClick={onGoToChat}>
                      Check eligibility to find schemes
                    </button>
                  )}
                </div>
              ) : (
                <ul className="checklist">
                  {docs.map((d) => (
                    <li key={d.key || d.name}>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={Boolean(d.checked)}
                          onChange={() => handleToggleDocument(d.name, !d.checked)}
                        />
                        <span>{d.name}</span>
                        {Array.isArray(d.schemes) && d.schemes.length > 1 && (
                          <small className="shared-hint">shared by {d.schemes.length} schemes</small>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        <div className="tracker-list-block">
          {itemsLoading && <p className="status">Loading tracked schemes…</p>}
          {itemsError && (
            <p className="tracker-error" role="alert">⚠️ {itemsError} — is the backend running?</p>
          )}
          {!itemsLoading && !itemsError && items.length === 0 && (
            <div className="status">
              <p>
                {filter
                  ? "No schemes with this status."
                  : "No tracked schemes yet."}
              </p>
              {!filter && onGoToChat && (
                <button type="button" className="btn-primary tracker-cta" onClick={onGoToChat}>
                  Find schemes with the AI Check
                </button>
              )}
            </div>
          )}
          <div className="tracker-grid">
            {items.map((item) => (
              <TrackerCard key={item.id} item={item} onUpdate={handleUpdate} onRemove={handleRemove} onRefresh={refresh} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
