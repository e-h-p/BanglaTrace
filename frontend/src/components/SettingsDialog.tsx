import { useState } from "react";
import {
  Check,
  ExternalLink,
  KeyRound,
  LoaderCircle,
  PlugZap,
  Save,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { api } from "../api";
import type { Provider, Settings } from "../types";
import { providers } from "../providers";
import Modal from "./Modal";

export default function SettingsDialog({
  initial,
  onSaved,
  onClose,
}: {
  initial: Settings;
  onSaved: (s: Settings) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [search, setSearch] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const provider = providers[draft.provider];
  function selectProvider(value: Provider) {
    const account = draft.provider_accounts?.[value];
    setDraft((s) => ({
      ...s,
      provider: value,
      model: account?.model ?? "",
      key_configured: account?.key_configured ?? false,
      key_source: account?.key_source ?? null,
    }));
    setKey("");
    setModels([]);
    setSearch("");
    setError("");
    setMessage("");
  }
  const change = <K extends keyof Settings>(name: K, value: Settings[K]) =>
    setDraft((s) => ({ ...s, [name]: value }));
  async function action(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function save() {
    const {
      key_configured: _k,
      key_source: _s,
      expires_at: _e,
      provider_accounts: _p,
      ...settings
    } = draft;
    const saved = await api<Settings>("/settings/provider", {
      method: "POST",
      body: JSON.stringify({ ...settings, ...(key ? { api_key: key } : {}) }),
    });
    setKey("");
    setDraft(saved);
    onSaved(saved);
    return saved;
  }
  const number = (
    name: keyof Settings,
    label: string,
    min: number,
    max: number,
    hint?: string,
    step = 1,
  ) => (
    <label className="field">
      {label}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={draft[name] as number}
        onChange={(e) => change(name, Number(e.target.value) as never)}
      />
      {hint && <small>{hint}</small>}
    </label>
  );
  return (
    <Modal title="Settings" onClose={onClose} drawer>
      <div className="settings-content">
        <div className="privacy-note">
          <ShieldCheck size={22} />
          <p>
            Your key stays in this session’s server memory and expires
            automatically. Only shortlisted sentence pairs are sent to the
            selected provider when you generate a report. Keys are kept
            separately for each provider.
          </p>
        </div>
        <div className="section-label">
          <KeyRound size={17} />
          <h3>AI provider</h3>
          <span className={`pill ${draft.key_configured ? "success" : ""}`}>
            {draft.key_configured ? "Key configured" : "Not configured"}
          </span>
        </div>
        <div className="provider-options" role="group" aria-label="AI provider">
          {(Object.keys(providers) as Provider[]).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={draft.provider === value}
              disabled={!!busy}
              onClick={() => selectProvider(value)}
            >
              {providers[value].name}
            </button>
          ))}
        </div>
        <p className="tiny muted">{provider.modelHint}</p>
        <label className="field">
          API key
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder={
              draft.key_configured
                ? "••••••••  Saved securely — enter to replace"
                : `Paste your ${provider.name} API key`
            }
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <small>
            Never saved in browser storage.{" "}
            <a href={provider.keyUrl} target="_blank" rel="noreferrer">
              Get an API key <ExternalLink size={11} />
            </a>
          </small>
        </label>
        <label className="field">
          {draft.provider === "openrouter" ? "Model route ID" : "Model ID"}
          <input
            value={draft.model}
            onChange={(e) => change("model", e.target.value)}
            placeholder={
              draft.provider === "openrouter"
                ? "provider/model-name"
                : "Enter a model ID or load the catalog"
            }
            list="model-routes"
            autoComplete="off"
          />
          <small>{provider.modelHint}</small>
        </label>
        <div className="model-tools">
          <button
            className="button secondary small"
            disabled={!!busy}
            onClick={() =>
              action("models", async () => {
                await save();
                const result = await api<{
                  models: { id: string; name: string }[];
                }>("/settings/models");
                setModels(result.models);
                setMessage(
                  `${result.models.length} models loaded from ${provider.name}.`,
                );
              })
            }
          >
            {busy === "models" ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Search size={15} />
            )}
            Save & load model catalog
          </button>
          <span>Explicit request to {provider.name}</span>
        </div>
        {models.length > 0 && (
          <div className="model-search">
            <input
              aria-label="Search available models"
              placeholder="Search model names or routes…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="model-results">
              {models
                .filter((m) =>
                  (m.id + " " + m.name)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .slice(0, 50)
                .map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      change("model", m.id);
                      setSearch(m.id);
                    }}
                  >
                    <span>{m.name}</span>
                    <small>{m.id}</small>
                    {draft.model === m.id && <Check size={16} />}
                  </button>
                ))}
            </div>
          </div>
        )}
        <datalist id="model-routes">
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </datalist>
        <div className="settings-actions">
          <button
            className="button secondary"
            disabled={!!busy}
            onClick={() =>
              action("test", async () => {
                await save();
                const result = await api<{ ok: boolean; message: string }>(
                  "/settings/test",
                  { method: "POST" },
                );
                if (!result.ok) throw new Error(result.message);
                setMessage(result.message);
              })
            }
          >
            {busy === "test" ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <PlugZap size={16} />
            )}
            Save & test connection
          </button>
          <button
            className="text-button danger-text"
            disabled={!!busy || !draft.key_configured}
            onClick={() =>
              action("clear", async () => {
                await save();
                const s = await api<Settings>("/settings/provider", {
                  method: "DELETE",
                });
                setKey("");
                setDraft(s);
                onSaved(s);
                setMessage(
                  "The API key and verification cache were cleared for this session.",
                );
              })
            }
          >
            <Trash2 size={14} />
            Clear API key
          </button>
        </div>
        <p className="tiny muted">
          The connection test sends a short Bangla example to the chosen model
          and may incur provider charges.
        </p>
        <button
          className="advanced-toggle"
          aria-expanded={advanced}
          onClick={() => setAdvanced(!advanced)}
        >
          <span>Advanced research settings</span>
          <span>{advanced ? "−" : "+"}</span>
        </button>
        {advanced && (
          <div className="advanced-fields">
            <p className="tiny muted">
              These retrieval defaults are engineering choices. Calibrate them
              against annotated data; similarity scores are not probabilities.
            </p>
            <label className="field">
              Retrieval mode
              <select
                value={draft.mode}
                onChange={(e) =>
                  change("mode", e.target.value as Settings["mode"])
                }
              >
                <option value="hybrid">Hybrid · LaBSE + LCS</option>
                <option value="dense">LaBSE + cosine only</option>
                <option value="lcs">LCS + lexical prefilter only</option>
              </select>
            </label>
            <div className="field-grid">
              {number("dense_top_k", "Dense Top-K", 1, 50)}
              {number("lexical_prefilter_k", "BM25 prefilter Top-K", 1, 100)}
              {number("lexical_top_k", "LCS Top-K retained", 1, 50)}
              {number(
                "max_candidates",
                "Maximum pairs / query sentence",
                2,
                30,
              )}
              {number("parallel_requests", "Parallel LLM requests", 1, 8)}
              {number("timeout_seconds", "Request timeout (seconds)", 5, 180)}
              {number("temperature", "Temperature", 0, 2, undefined, 0.1)}
              {number("max_tokens", "Maximum output tokens", 100, 4000)}
            </div>
            <div className="field-grid">
              <label className="field">
                Minimum cosine (optional)
                <input
                  type="number"
                  min={-1}
                  max={1}
                  step="0.01"
                  placeholder="No minimum"
                  value={draft.min_cosine ?? ""}
                  onChange={(e) =>
                    change(
                      "min_cosine",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                />
              </label>
              <label className="field">
                Minimum LCS (optional)
                <input
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  placeholder="No minimum"
                  value={draft.min_lcs ?? ""}
                  onChange={(e) =>
                    change(
                      "min_lcs",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                />
              </label>
            </div>
            <label className="check-field">
              <input
                type="checkbox"
                checked={draft.json_mode}
                onChange={(e) => change("json_mode", e.target.checked)}
              />
              Request JSON mode for OpenRouter / OpenAI (Claude uses the JSON
              instruction and parser)
            </label>
            <label className="field">
              Verification instruction
              <textarea
                rows={10}
                value={draft.prompt}
                onChange={(e) => change("prompt", e.target.value)}
              />
              <small>
                Sentence pairs are appended as JSON data. Changes are recorded
                in report metadata.
              </small>
            </label>
          </div>
        )}
        {error && (
          <div role="alert" className="alert error">
            {error}
          </div>
        )}
        {message && (
          <div role="status" className="alert success">
            {message}
          </div>
        )}
        <div className="modal-footer">
          <span>
            <ShieldCheck size={14} />
            Session-scoped · no browser key storage
          </span>
          <button
            className="button primary"
            disabled={!!busy}
            onClick={() =>
              action("save", async () => {
                await save();
                setMessage("Settings saved for this session.");
              })
            }
          >
            {busy === "save" ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            Save settings
          </button>
        </div>
      </div>
    </Modal>
  );
}
