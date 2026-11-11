import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CircleAlert,
  FileClock,
  FileText,
  LoaderCircle,
  LogOut,
  Moon,
  Settings2,
  ShieldCheck,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { api, upload } from "./api";
import type {
  Document,
  ProgressEvent,
  Report,
  ReportItem,
  SessionInfo,
  Settings,
  Source,
} from "./types";
import SettingsDialog from "./components/SettingsDialog";
import Workspace from "./components/Workspace";
import Library from "./components/Library";
import ReportView from "./components/ReportView";
import Modal from "./components/Modal";

export default function App() {
  const qc = useQueryClient();
  const [view, setView] = useState<
    "workspace" | "library" | "reports" | "report"
  >("workspace");
  const [showSettings, setShowSettings] = useState(false),
    [preview, setPreview] = useState<Document | null>(null);
  const [text, setText] = useState(""),
    [input, setInput] = useState<Document | null>(null),
    [tab, setTab] = useState<"text" | "file">("text");
  const [counts, setCounts] = useState({ word_count: 0, sentence_count: 0 });
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [dismissedAlert, setDismissedAlert] = useState("");
  const [job, setJob] = useState<string | null>(null),
    [events, setEvents] = useState<ProgressEvent[]>([]),
    [streamLost, setStreamLost] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("banglaplag-theme");
    return saved
      ? saved === "dark"
      : (window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("banglaplag-theme", dark ? "dark" : "light");
  }, [dark]);
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<SessionInfo>("/session", { method: "POST" }),
    staleTime: Infinity,
    retry: false,
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
    enabled: !!session.data,
  });
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<{ sources: Source[] }>("/sources"),
    enabled: !!session.data,
  });
  const history = useQuery({
    queryKey: ["reports"],
    queryFn: () => api<{ reports: ReportItem[] }>("/reports"),
    enabled: !!session.data,
  });
  const progress = useQuery({
    queryKey: ["job", job],
    queryFn: () => api<Report | { status: string }>(`/reports/${job}`),
    enabled: !!job,
    refetchInterval: (q) =>
      q.state.data && "matches" in q.state.data ? false : 2000,
  });
  useEffect(() => {
    if (progress.data && "matches" in progress.data) {
      setReport(progress.data);
      setView("report");
      setJob(null);
      setBusy("");
      void qc.invalidateQueries({ queryKey: ["sources"] });
      void qc.invalidateQueries({ queryKey: ["reports"] });
    }
  }, [progress.data, qc]);
  useEffect(() => {
    const active = history.data?.reports.find((r) =>
      ["queued", "running"].includes(r.status),
    );
    if (active && !job && !report) {
      setJob(active.report_id);
      setBusy("Processing report");
    }
  }, [history.data, job, report]);
  useEffect(() => {
    if (!job) return;
    setEvents([]);
    setStreamLost(false);
    const stream = new EventSource(`/api/reports/${job}/events`);
    stream.onmessage = (e) => {
      const value = JSON.parse(e.data) as ProgressEvent;
      setEvents((old) =>
        old.some((v) => v.id === value.id) ? old : [...old, value],
      );
      setStreamLost(false);
      if (value.terminal) {
        stream.close();
        void qc.invalidateQueries({ queryKey: ["job", job] });
      }
    };
    stream.onerror = () => setStreamLost(true);
    return () => stream.close();
  }, [job, qc]);
  useEffect(() => {
    if (!session.data) return;
    const controller = new AbortController();
    const id = setTimeout(() => {
      void api<{ word_count: number; sentence_count: number }>(
        "/input/analyze",
        {
          method: "POST",
          body: JSON.stringify({ text }),
          signal: controller.signal,
        },
      )
        .then(setCounts)
        .catch(() => {});
    }, 500);
    return () => {
      clearTimeout(id);
      controller.abort();
    };
  }, [text, session.data]);
  const s = settings.data ?? session.data?.settings;
  async function run(label: string, fn: () => Promise<void>) {
    setDismissedAlert("");
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy((old) => (old === "Processing report" ? old : ""));
    }
  }
  async function uploadSources(files: File[]) {
    await run("Uploading sources", async () => {
      for (const file of files) {
        setBusy(`Uploading ${file.name}`);
        const result = await upload<{ source: Source; duplicate: boolean }>(
          "/sources/upload",
          file,
        );
        if (result.duplicate)
          setNotice(`${file.name} is already in your collection.`);
        await qc.invalidateQueries({ queryKey: ["sources"] });
      }
    });
  }
  async function generate(previewOnly: boolean) {
    setError("");
    setNotice("");
    if (!sources.data?.sources.length) {
      setError("Upload at least one source document first.");
      return;
    }
    if (tab === "text" ? !text.trim() : !input) {
      setError("Paste Bangla text or upload a document to check.");
      return;
    }
    if (!previewOnly && (!s?.key_configured || !s.model)) {
      setError(
        "Configure your selected provider's API key and model to verify matches, or use retrieval preview.",
      );
      setShowSettings(true);
      return;
    }
    await run("Starting report", async () => {
      const result = await api<{ report_id: string }>("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          ...(tab === "text" ? { text } : { input_id: input!.document_id }),
          preview_only: previewOnly,
        }),
      });
      setJob(result.report_id);
      setBusy("Processing report");
      setReport(null);
    });
  }
  async function openReport(id: string) {
    await run("Opening report", async () => {
      const result = await api<Report | { status: string }>(`/reports/${id}`);
      if ("matches" in result) {
        setReport(result);
        setView("report");
      } else {
        setJob(id);
        setBusy("Processing report");
      }
    });
  }
  async function clearSession() {
    if (
      !window.confirm(
        "Clear this workspace? Uploaded documents, keys, cached embeddings and saved reports will be removed. Download any reports you need first.",
      )
    )
      return;
    await run("Clearing workspace", async () => {
      await api("/session", { method: "DELETE" });
      setJob(null);
      setReport(null);
      setText("");
      setInput(null);
      setView("workspace");
      qc.clear();
      await qc.fetchQuery({
        queryKey: ["session"],
        queryFn: () => api<SessionInfo>("/session", { method: "POST" }),
      });
      setNotice("Your previous session data has been deleted.");
    });
  }
  const alert =
    error ||
    (sources.error?.message ??
      settings.error?.message ??
      history.error?.message ??
      progress.error?.message);
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("workspace");
          }}
          aria-label="BanglaTrace home"
        >
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect
              x="3"
              y="7"
              width="26"
              height="3.4"
              rx="1.2"
              fill="currentColor"
            />
            <path
              d="M16 10.4v9.2a4.6 4.6 0 0 1-4.6 4.6H9.6"
              fill="none"
              stroke="currentColor"
              strokeWidth="3.2"
              strokeLinecap="round"
            />
            <path
              d="M19.5 21.5l3 3 5.5-6.5"
              fill="none"
              stroke="var(--red)"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="brand-name">BanglaTrace</span>
          <span className="brand-bn" lang="bn">
            বাংলাট্রেস
          </span>
        </a>
        <nav className="tabs" aria-label="Main">
          <button
            className="tab"
            aria-current={
              view === "workspace" || view === "report" ? "page" : undefined
            }
            onClick={() => setView(report ? "report" : "workspace")}
          >
            Check
          </button>
          <button
            className="tab"
            aria-current={view === "library" ? "page" : undefined}
            onClick={() => setView("library")}
          >
            Library
          </button>
        </nav>
        <div className="top-right">
          <button
            className="status"
            disabled={!s || !!job}
            onClick={() => setShowSettings(true)}
            title="Change in settings"
          >
            <span className="dot" />
            <span className="status-text">
              {s?.mode === "lcs"
                ? "Lexical search"
                : s?.mode === "dense"
                  ? "Meaning search"
                  : "Hybrid search"}
              ,{" "}
              {s?.key_configured && s?.model
                ? "AI review configured"
                : "AI review not configured"}
            </span>
          </button>
          <button
            className="icon-btn"
            aria-label="Reports"
            title="Session reports"
            onClick={() => {
              setView("reports");
              void qc.invalidateQueries({ queryKey: ["reports"] });
            }}
          >
            <FileClock />
          </button>
          <button
            className="icon-btn theme-toggle"
            onClick={() => setDark(!dark)}
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {dark ? <Sun /> : <Moon />}
          </button>
          <button
            className="icon-btn"
            disabled={!s || !!job}
            onClick={() => setShowSettings(true)}
            aria-label="Settings"
          >
            <Settings2 />
          </button>
        </div>
      </header>
      <main id="main">
        {session.isPending ? (
          <div className="loading-screen">
            <LoaderCircle className="spin" />
            <h2>Opening your workspace…</h2>
          </div>
        ) : session.isError ? (
          <div className="card connection-error">
            <CircleAlert />
            <h2>Couldn’t reach the backend</h2>
            <p>{session.error.message}</p>
            <p>Start FastAPI on port 8000, then reload this page.</p>
            <button
              className="btn primary"
              onClick={() => void session.refetch()}
            >
              Retry connection
            </button>
          </div>
        ) : (
          <>
            {alert && alert !== dismissedAlert && (
              <div role="alert" className="alert error global-alert">
                <CircleAlert />
                <span>{alert}</span>
                <button
                  className="icon-btn"
                  aria-label="Dismiss error"
                  onClick={() => {
                    setDismissedAlert(alert);
                    setError("");
                  }}
                >
                  <X />
                </button>
              </div>
            )}
            {notice && (
              <div role="status" className="alert success global-alert">
                <Check />
                {notice}
              </div>
            )}
            {job ? (
              <div className="layout processing-layout">
                <article className="sheet">
                  <div className="sheet-head">
                    <h2>Checking document</h2>
                  </div>
                  <div className="processing-document" lang="bn">
                    {tab === "file" ? input?.text : text}
                  </div>
                </article>
                <aside className="panel">
                  <div className="card processing-card">
                    <div className="section-label">
                      <LoaderCircle className="spin" />
                      <h2>Following the evidence.</h2>
                    </div>
                    <p className="muted" role="status" aria-live="polite">
                      {events.at(-1)?.stage ||
                        "Connecting to the report worker…"}
                    </p>
                    {events.at(-1)?.total !== undefined && (
                      <p className="count">
                        Verifying {events.at(-1)?.completed} of{" "}
                        {events.at(-1)?.total} candidate pairs
                      </p>
                    )}
                    <div className="indeterminate-track">
                      <span />
                    </div>
                    <p className="progress-note">
                      {s?.mode !== "lcs"
                        ? "The first LaBSE run downloads the model and can take several minutes."
                        : "Lexical retrieval runs locally."}{" "}
                      You can keep this tab open.
                    </p>
                    {streamLost && (
                      <p className="warning-text">
                        Live event connection interrupted. Checking report
                        status automatically…
                      </p>
                    )}
                    <div className="progress-log">
                      {events.slice(-6).map((event, i, all) => (
                        <div
                          key={event.id}
                          className={i === all.length - 1 ? "current" : ""}
                        >
                          {i === all.length - 1 ? (
                            <LoaderCircle size={14} className="spin" />
                          ) : (
                            <Check size={14} />
                          )}
                          <span>{event.stage}</span>
                          {event.total !== undefined && (
                            <small>
                              {event.completed}/{event.total}
                            </small>
                          )}
                        </div>
                      ))}
                    </div>
                    <button
                      className="btn ghost"
                      onClick={() => {
                        void api(`/reports/${job}/cancel`, { method: "POST" })
                          .then(() =>
                            setNotice(
                              "Cancellation requested. The current operation will finish safely.",
                            ),
                          )
                          .catch((e) => setError(e.message));
                      }}
                    >
                      Cancel report
                    </button>
                  </div>
                </aside>
              </div>
            ) : view === "workspace" && s && session.data ? (
              <Workspace
                sources={sources.data?.sources ?? []}
                settings={s}
                limits={session.data.limits}
                text={text}
                setText={setText}
                input={input}
                tab={tab}
                setTab={setTab}
                counts={counts}
                busy={busy}
                uploadSources={(files) => void uploadSources(files)}
                uploadInput={(file) =>
                  void run(`Uploading ${file.name}`, async () => {
                    setInput(await upload<Document>("/input/upload", file));
                  })
                }
                removeInput={() =>
                  void run("Removing input", async () => {
                    await api("/input", { method: "DELETE" });
                    setInput(null);
                  })
                }
                removeSource={(id) =>
                  void run("Removing source", async () => {
                    await api(`/sources/${id}`, { method: "DELETE" });
                    await qc.invalidateQueries({ queryKey: ["sources"] });
                  })
                }
                preview={(id) =>
                  void run("Loading preview", async () =>
                    setPreview(await api<Document>(`/sources/${id}`)),
                  )
                }
                generate={(p) => void generate(p)}
                openSettings={() => setShowSettings(true)}
                openLibrary={() => setView("library")}
              />
            ) : view === "library" && session.data ? (
              <Library
                sources={sources.data?.sources ?? []}
                limits={session.data.limits}
                busy={busy}
                uploadSources={(files) => void uploadSources(files)}
                removeSource={(id) =>
                  void run("Removing source", async () => {
                    await api(`/sources/${id}`, { method: "DELETE" });
                    await qc.invalidateQueries({ queryKey: ["sources"] });
                  })
                }
                preview={(id) =>
                  void run("Loading preview", async () =>
                    setPreview(await api<Document>(`/sources/${id}`)),
                  )
                }
              />
            ) : view === "report" && report ? (
              <ReportView
                key={report.report_id}
                report={report}
                back={() => setView("workspace")}
              />
            ) : (
              <section className="lib reports-list">
                <div className="lib-head">
                  <div>
                    <h1>Session reports</h1>
                    <p className="muted">
                      Results stay here until your session expires or you clear
                      them.
                    </p>
                  </div>
                  <button
                    className="btn primary"
                    onClick={() => setView("workspace")}
                  >
                    New analysis <ArrowRight />
                  </button>
                </div>
                {history.data?.reports.length ? (
                  <div className="card history-list">
                    {history.data.reports.map((item) => (
                      <div className="history-row" key={item.report_id}>
                        <FileText />
                        <div>
                          <strong>
                            {item.query_filename || "Analysis in progress"}
                          </strong>
                          <small>
                            {item.created_at
                              ? new Date(item.created_at).toLocaleString()
                              : "Processing"}{" "}
                            · {item.status}
                          </small>
                        </div>
                        <span className="tag">
                          {item.status === "completed" &&
                          item.estimated_matched_coverage !== null
                            ? `${item.estimated_matched_coverage}% coverage`
                            : "Partial / pending"}
                        </span>
                        <button
                          className="btn ghost"
                          onClick={() => void openReport(item.report_id)}
                        >
                          Open <ArrowRight />
                        </button>
                        <button
                          className="icon-btn"
                          aria-label="Delete report"
                          onClick={() =>
                            void run("Deleting report", async () => {
                              await api(`/reports/${item.report_id}`, {
                                method: "DELETE",
                              });
                              await qc.invalidateQueries({
                                queryKey: ["reports"],
                              });
                              if (report?.report_id === item.report_id)
                                setReport(null);
                            })
                          }
                        >
                          <Trash2 />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="card reports-empty">
                    <FileClock />
                    <h2>No reports yet</h2>
                    <p className="muted">
                      Your completed analyses will appear here.
                    </p>
                    <button
                      className="btn primary"
                      onClick={() => setView("workspace")}
                    >
                      Start your first analysis <ArrowRight />
                    </button>
                  </div>
                )}
              </section>
            )}
            <footer className="app-footer">
              <span>
                <ShieldCheck size={14} />
                Evidence for review. Thoughtful decisions stay human.
              </span>
              <button
                className="text-button"
                disabled={!!busy || !!job}
                onClick={() => void clearSession()}
              >
                <LogOut size={13} />
                Clear session data
              </button>
            </footer>
          </>
        )}
      </main>
      {showSettings && s && (
        <SettingsDialog
          initial={s}
          onClose={() => setShowSettings(false)}
          onSaved={(value) => {
            qc.setQueryData(["settings"], value);
            void qc.invalidateQueries({ queryKey: ["settings"] });
          }}
        />
      )}
      {preview && (
        <Modal title={preview.filename} onClose={() => setPreview(null)} wide>
          <div className="preview-meta">
            {preview.sentences.length} sentences · {preview.file_type}
            {preview.page_count ? ` · ${preview.page_count} pages` : ""}
          </div>
          {preview.warnings.map((w) => (
            <div key={w} className="alert warning">
              {w}
            </div>
          ))}
          <div className="document-preview" lang="bn">
            {preview.text}
          </div>
        </Modal>
      )}
    </>
  );
}
