import { useRef, useState } from "react";
import { Eye, Plus, Trash2, LoaderCircle } from "lucide-react";
import type { Source, SessionInfo } from "../types";

export default function Library(p: {
  sources: Source[];
  limits: SessionInfo["limits"];
  busy: string;
  uploadSources: (files: File[]) => void;
  removeSource: (id: string) => void;
  preview: (id: string) => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <section
      className={`lib ${drag ? "lib-dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (!p.busy) p.uploadSources(Array.from(e.dataTransfer.files));
      }}
    >
      <div className="lib-head">
        <div>
          <h1>Reference library</h1>
          <p className="muted">
            Every document is checked against these sources. Add theses,
            articles or past submissions.
          </p>
        </div>
        <button
          className="btn primary"
          disabled={!!p.busy}
          onClick={() => picker.current?.click()}
        >
          <Plus />
          Add documents
        </button>
        <input
          className="sr-only"
          ref={picker}
          type="file"
          accept=".pdf,.txt"
          multiple
          aria-label="Add source documents"
          onChange={(e) => {
            if (e.target.files) p.uploadSources(Array.from(e.target.files));
            e.target.value = "";
          }}
        />
      </div>
      <div className="lib-stats">
        {p.sources.length} documents,{" "}
        {p.sources.reduce((n, s) => n + s.sentence_count, 0).toLocaleString()}{" "}
        sentences.{" "}
        {p.sources.length
          ? `${p.sources.filter((s) => s.built_in).length} built-in demo documents. Your uploads are private to this session.`
          : "Add your own to make checks more useful."}
      </div>
      {p.busy && (
        <div className="inline-status" role="status">
          <LoaderCircle className="spin" />
          {p.busy}
        </div>
      )}
      <ul className="lib-list">
        {p.sources.map((s) => (
          <li key={s.document_id}>
            <div className="doc-ic" aria-hidden="true" />
            <div className="lib-document">
              <div className="lib-title">{s.filename}</div>
              <div className="lib-meta">
                {s.sentence_count} sentences · {s.file_type} ·{" "}
                {(s.size_bytes / 1024).toFixed(1)} KB
                {s.page_count ? ` · ${s.page_count} pages` : ""} · {s.status}
              </div>
              {s.warnings.map((w) => (
                <p className="warning-text" key={w}>
                  {w}
                </p>
              ))}
            </div>
            <span className={`tag ${s.built_in ? "" : "mine"}`}>
              {s.built_in ? "Built-in demo" : "Your upload"}
            </span>
            <div className="lib-actions">
              <button
                className="icon-btn"
                aria-label={`Preview ${s.filename}`}
                title="Preview extracted text"
                onClick={() => p.preview(s.document_id)}
              >
                <Eye />
              </button>
              {!s.built_in && (
                <button
                  className="icon-btn"
                  aria-label={`Remove ${s.filename}`}
                  title="Remove source"
                  disabled={!!p.busy}
                  onClick={() => p.removeSource(s.document_id)}
                >
                  <Trash2 />
                </button>
              )}
            </div>
          </li>
        ))}
        {!p.sources.length && (
          <li className="library-empty">
            <div className="doc-ic" />
            <div>
              <strong>No reference documents yet</strong>
              <p className="muted">
                Drop PDF or TXT files here, or choose Add documents.
              </p>
            </div>
          </li>
        )}
      </ul>
      <div className="lib-foot">
        <span>
          Text-based PDF / UTF-8 TXT · up to {p.limits.max_upload_mb} MB each ·{" "}
          {p.limits.max_sources} sources per session
        </span>
        {p.sources.length > 0 && (
          <button
            className="text-button"
            disabled={!!p.busy}
            onClick={() => picker.current?.click()}
          >
            <Plus size={14} />
            Add Another File
          </button>
        )}
      </div>
    </section>
  );
}
