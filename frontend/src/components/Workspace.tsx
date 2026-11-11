import { useRef, useState } from "react";
import { Upload, X, ArrowRight } from "lucide-react";
import type { Document, SessionInfo, Settings, Source } from "../types";
import mixedEssay from "../samples/suspect_essay.txt?raw";
import originalEssay from "../samples/original_essay.txt?raw";
import ColourLegend from "./ColourLegend";

export type WorkspaceProps = {
  sources: Source[];
  settings: Settings;
  limits: SessionInfo["limits"];
  text: string;
  setText: (s: string) => void;
  input: Document | null;
  tab: "text" | "file";
  setTab: (s: "text" | "file") => void;
  counts: { word_count: number; sentence_count: number };
  busy: string;
  uploadSources: (files: File[]) => void;
  uploadInput: (file: File) => void;
  removeInput: () => void;
  removeSource: (id: string) => void;
  preview: (id: string) => void;
  generate: (preview: boolean) => void;
  openSettings: () => void;
  openLibrary: () => void;
};

export default function Workspace(p: WorkspaceProps) {
  const inputPicker = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [title, setTitle] = useState("Untitled document");
  const fileMode = p.tab === "file";
  const chooseInput = (file?: File) => {
    if (!file || p.busy) return;
    p.setTab("file");
    p.uploadInput(file);
    setTitle(file.name.replace(/\.[^.]+$/, ""));
  };
  const sample = (text: string, name: string) => {
    p.setTab("text");
    p.setText(text);
    setTitle(name);
  };
  return (
    <div className="layout" aria-label="Check workspace">
      <article className="sheet" aria-label="Document">
        <div className="sheet-head">
          <input
            className="doc-title"
            aria-label="Document title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            spellCheck={false}
          />
          {fileMode && (
            <button className="btn ghost" onClick={() => p.setTab("text")}>
              Edit text
            </button>
          )}
        </div>
        <div id="compose">
          <div
            className={`drop ${drag ? "over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              chooseInput(e.dataTransfer.files[0]);
            }}
          >
            {fileMode ? (
              <div className="input-file-area">
                {p.input ? (
                  <>
                    <div className="input-file-heading">
                      <strong>{p.input.filename}</strong>
                      <span>{p.input.sentences.length} sentences</span>
                      <button
                        className="icon-btn"
                        aria-label="Remove suspicious file"
                        disabled={!!p.busy}
                        onClick={p.removeInput}
                      >
                        <X />
                      </button>
                    </div>
                    <div className="input-preview" lang="bn">
                      {p.input.text}
                    </div>
                    {p.input.warnings.map((w) => (
                      <p key={w} className="warning-text">
                        {w}
                      </p>
                    ))}
                    <button
                      className="text-button"
                      disabled={!!p.busy}
                      onClick={() => inputPicker.current?.click()}
                    >
                      Choose a different file
                    </button>
                  </>
                ) : (
                  <button
                    className="input-drop"
                    disabled={!!p.busy}
                    onClick={() => inputPicker.current?.click()}
                  >
                    <Upload />
                    <strong>Upload the document to check</strong>
                    <span>Choose or drop one PDF / TXT file</span>
                  </button>
                )}
              </div>
            ) : (
              <textarea
                id="input"
                aria-label="Suspicious Bangla text"
                lang="bn"
                spellCheck={false}
                value={p.text}
                onChange={(e) => p.setText(e.target.value)}
                maxLength={500000}
                onKeyDown={(e) => {
                  if (
                    (e.ctrlKey || e.metaKey) &&
                    e.key === "Enter" &&
                    !p.busy
                  ) {
                    e.preventDefault();
                    p.generate(false);
                  }
                }}
                placeholder={
                  "এখানে বাংলা লেখা পেস্ট করুন, অথবা একটি ফাইল টেনে আনুন।\n\nPaste Bangla text here, or drop a .txt or .pdf file."
                }
              />
            )}
            <span className="drop-hint" aria-hidden="true">
              Drop to open this file
            </span>
          </div>
          <div className="compose-bar">
            <div className="compose-left">
              <button
                className="btn ghost file-btn"
                disabled={!!p.busy}
                onClick={() => inputPicker.current?.click()}
              >
                <Upload />
                Upload file
              </button>
              <input
                ref={inputPicker}
                className="sr-only"
                type="file"
                accept=".txt,.pdf"
                aria-label="Upload document to check"
                onChange={(e) => {
                  chooseInput(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              <span className="samples">
                Try a sample:
                <button
                  className="chip"
                  disabled={!!p.busy}
                  onClick={() => sample(mixedEssay, "Mixed essay")}
                >
                  Mixed essay
                </button>
                <button
                  className="chip"
                  disabled={!!p.busy}
                  onClick={() => sample(originalEssay, "Original essay")}
                >
                  Original essay
                </button>
              </span>
            </div>
            <div className="compose-right">
              <span className="count">
                {fileMode
                  ? (p.input?.sentences.length ?? 0)
                  : p.counts.sentence_count}{" "}
                sentences
              </span>
              <button
                className="btn primary"
                disabled={!!p.busy}
                onClick={() => p.generate(false)}
              >
                Check document
              </button>
            </div>
          </div>
          <div className="preview-bar">
            <span>
              {p.busy ||
                (fileMode
                  ? "PDF / TXT document"
                  : `${p.counts.word_count} words`)}
            </span>
            <button
              className="text-button"
              disabled={!!p.busy}
              onClick={() => p.generate(true)}
            >
              Try retrieval preview <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </article>
      <aside className="panel" aria-label="About this check">
        <div className="card intro">
          <h2>Find copied and reworded Bangla text, sentence by sentence.</h2>
          <p className="muted">
            Paste a thesis chapter, assignment or article. Each sentence is
            checked against <b>{p.sources.length} documents</b> (
            {p.sources
              .reduce((n, s) => n + s.sentence_count, 0)
              .toLocaleString()}{" "}
            sentences) in your library.
          </p>
          <ol className="steps">
            <li>
              <span>
                <b>Find</b>Looks up the closest passages in the library.
              </span>
            </li>
            <li>
              <span>
                <b>Compare</b>Retrieves candidates using LaBSE cosine and
                lexical LCS.
              </span>
            </li>
            <li>
              <span>
                <b>Verify</b>Your chosen AI model checks meaning, facts and
                contradictions.
              </span>
            </li>
            <li>
              <span>
                <b>Review</b>Select a marked sentence to see its sources and
                evidence.
              </span>
            </li>
          </ol>
        </div>
        <div className="card">
          <ColourLegend compact />
        </div>
        <div className="card library-overview">
          <h3>Reference library</h3>
          <p className="muted">
            {p.sources.length
              ? "Your source collection is ready for comparison."
              : "Add source documents before checking your text."}
          </p>
          <button className="btn ghost" onClick={p.openLibrary}>
            Manage library <ArrowRight />
          </button>
        </div>
        <div className="card check-note">
          <h3>
            {p.settings.key_configured && p.settings.model
              ? "AI review connected"
              : "AI review"}
          </h3>
          <p className="muted">
            {p.settings.key_configured && p.settings.model
              ? p.settings.model
              : "Choose OpenRouter, OpenAI or Claude in Settings and add its API key and model, or try a retrieval preview without a key."}
          </p>
          <button className="text-button" onClick={p.openSettings}>
            Open settings <ArrowRight size={13} />
          </button>
        </div>
      </aside>
    </div>
  );
}
