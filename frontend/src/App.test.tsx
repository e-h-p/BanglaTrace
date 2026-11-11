// @vitest-environment jsdom
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import type { Document, Report, Settings, Source } from "./types";

let settings: Settings, documents: Source[];
const query = "বাংলাদেশের রাজধানী ঢাকা।";
function document(source: Source): Document {
  return {
    ...source,
    text: query,
    sentences: [
      {
        document_id: source.document_id,
        filename: source.filename,
        sentence_id: source.document_id + "_S1",
        sentence_number: 1,
        original_text: query,
        normalized_text: query,
        char_start: 0,
        char_end: query.length,
        word_count: 3,
        page_number: null,
        page_end: null,
        line_start: 1,
        line_end: 1,
        location_type: "physical",
      },
    ],
  };
}
function report(): Report {
  const docs = documents.map(document);
  return {
    report_id: "ui-fixture-report",
    status: "partial",
    preview_only: true,
    cancelled: false,
    error: null,
    created_at: "2026-10-29T12:00:00Z",
    processing_seconds: 0.5,
    estimated_matched_coverage: 0,
    matched_query_word_count: 0,
    total_eligible_query_word_count: 3,
    total_sentences: 1,
    matched_sentences: 0,
    partial_sentences: 0,
    unmatched_sentences: 0,
    unverified_sentences: 1,
    matching_source_documents: 0,
    total_source_documents: documents.length,
    verification_complete: false,
    unverified_candidate_pairs: documents.length,
    query_text: query,
    query_filename: "Pasted text.txt",
    matches: [
      {
        query: {
          ...docs[0].sentences[0],
          document_id: "Q",
          sentence_id: "Q_S1",
        },
        status: "unverified",
        sources: docs.map((d, i) => ({
          source: d.sentences[0],
          cosine_similarity: 1,
          lcs_similarity: 1,
          dense_rank: i + 1,
          lexical_rank: i + 1,
          fused_rank: i + 1,
          fused_score: 0.03,
          verification: {
            status: "unverified",
            relation: null,
            reason: "Preview only.",
            actual_model: null,
            attempts: 0,
          },
        })),
      },
    ],
    source_documents: docs,
    metadata: {
      pipeline_version: "test",
      verification_configuration: settings,
      diagnostics: {},
      stage_seconds: {},
      usage: {},
      actual_models: [],
      coverage_method: "Fixture coverage explanation.",
      disclaimer: "Text overlap is evidence for review.",
      embedding_model: "sentence-transformers/LaBSE",
      embedding_revision: "test",
    },
  };
}
beforeEach(() => {
  settings = {
    provider: "openrouter",
    provider_accounts: {
      openrouter: { model: "", key_configured: false, key_source: null },
      openai: { model: "", key_configured: false, key_source: null },
      anthropic: { model: "", key_configured: false, key_source: null },
    },
    model: "",
    prompt:
      "Compare meanings and reject contradictions. Return structured JSON.",
    temperature: 0,
    max_tokens: 300,
    dense_top_k: 10,
    lexical_prefilter_k: 20,
    lexical_top_k: 10,
    max_candidates: 6,
    min_cosine: null,
    min_lcs: null,
    parallel_requests: 3,
    timeout_seconds: 45,
    mode: "hybrid",
    json_mode: false,
    key_configured: false,
    key_source: null,
    expires_at: Date.now() / 1000 + 7200,
  };
  documents = [];
  localStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.removeAttribute("open");
    },
  });
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "EventSource",
    class {
      onmessage = null;
      onerror = null;
      close() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit = {}) => {
      let result: unknown;
      if (path === "/api/session")
        result = {
          expires_at: settings.expires_at,
          limits: {
            max_upload_mb: 10,
            max_sources: 30,
            max_query_sentences: 500,
            max_source_sentences: 12000,
          },
          settings,
        };
      else if (path === "/api/settings") result = settings;
      else if (path === "/api/settings/provider") {
        const body = JSON.parse(init.body as string);
        const { api_key, ...rest } = body;
        const account =
          settings.provider_accounts?.[rest.provider as Settings["provider"]];
        const keyConfigured = !!api_key || !!account?.key_configured;
        const keySource = api_key ? "session" : (account?.key_source ?? null);
        settings = {
          ...settings,
          ...rest,
          key_configured: keyConfigured,
          key_source: keySource,
          provider_accounts: {
            ...settings.provider_accounts,
            [rest.provider]: {
              model: rest.model,
              key_configured: keyConfigured,
              key_source: keySource,
            },
          },
        };
        result = settings;
      } else if (path === "/api/sources") result = { sources: documents };
      else if (path === "/api/sources/upload") {
        const file = (init.body as FormData).get("file") as File;
        const source = {
          document_id: "D" + documents.length,
          filename: file.name,
          file_type: "TXT",
          size_bytes: file.size,
          page_count: null,
          sentence_count: 1,
          status: "extracted",
          warnings: [],
        };
        documents.push(source);
        result = { source, duplicate: false };
      } else if (path === "/api/reports") result = { reports: [] };
      else if (path === "/api/reports/generate")
        result = { report_id: "ui-fixture-report", status: "queued" };
      else if (path === "/api/reports/ui-fixture-report") result = report();
      else if (path === "/api/input/analyze")
        result = { word_count: 3, sentence_count: 1 };
      else if (path.startsWith("/api/sources/")) {
        const source = documents.find((d) => path.endsWith(d.document_id));
        if (!source) throw new Error("Missing source");
        result = document(source);
      } else throw new Error("Unexpected mocked route: " + path);
      return new Response(JSON.stringify(result), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  return { ...result, user: userEvent.setup() };
}

describe("connected workspace interactions", () => {
  it("selects direct API providers without reusing another provider's key or model", async () => {
    const { user } = mount();
    await screen.findByRole("heading", { name: /Find copied and reworded/ });
    await user.click(screen.getByRole("button", { name: "Settings" }));
    await user.type(screen.getByLabelText(/^API key/), "router-secret-fixture");
    await user.type(screen.getByLabelText(/^Model route ID/), "fixture/router");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Settings saved for this session.");
    await user.click(screen.getByRole("button", { name: "OpenAI / ChatGPT" }));
    expect((screen.getByLabelText(/^API key/) as HTMLInputElement).value).toBe(
      "",
    );
    expect((screen.getByLabelText(/^Model ID/) as HTMLInputElement).value).toBe(
      "",
    );
    await user.type(screen.getByLabelText(/^API key/), "openai-secret-fixture");
    await user.type(screen.getByLabelText(/^Model ID/), "fixture-gpt");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Settings saved for this session.");
    const calls = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => url === "/api/settings/provider");
    const body = JSON.parse(calls.at(-1)![1]!.body as string);
    expect(body.provider).toBe("openai");
    expect(body.api_key).toBe("openai-secret-fixture");
    expect(body.model).toBe("fixture-gpt");
    expect(body.provider_accounts).toBeUndefined();
    await user.click(
      screen.getByRole("button", { name: "Claude / Anthropic" }),
    );
    expect((screen.getByLabelText(/^Model ID/) as HTMLInputElement).value).toBe(
      "",
    );
    await user.click(screen.getByRole("button", { name: "OpenRouter" }));
    expect(
      (screen.getByLabelText(/^Model route ID/) as HTMLInputElement).value,
    ).toBe("fixture/router");
    expect(JSON.stringify(localStorage)).not.toContain("secret-fixture");
  });

  it("offers built-in source previews while reserving removal for user uploads", async () => {
    documents = [
      {
        document_id: "demo1",
        filename: "demo-rivers.txt",
        built_in: true,
        file_type: "TXT",
        size_bytes: 100,
        page_count: null,
        sentence_count: 1,
        status: "extracted",
        warnings: [],
      },
    ];
    const { user } = mount();
    await screen.findByRole("heading", { name: /Find copied and reworded/ });
    await user.click(screen.getByRole("button", { name: "Library" }));
    expect(await screen.findByText("Built-in demo")).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Remove demo-rivers.txt" }),
    ).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Preview demo-rivers.txt" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "demo-rivers.txt" }),
    ).toBeDefined();
    expect(screen.getByText(query)).toBeDefined();
  });

  it("validates inputs, uploads real File objects, and configures a key without browser storage", async () => {
    const { user } = mount();
    await screen.findByRole("heading", { name: /Find copied and reworded/ });
    await user.click(screen.getByRole("button", { name: "Check document" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Upload at least one source",
    );
    await user.click(screen.getByRole("button", { name: "Library" }));
    const picker = screen.getByLabelText(
      "Add source documents",
    ) as HTMLInputElement;
    await user.upload(
      picker,
      new File([query], "first.txt", { type: "text/plain" }),
    );
    await screen.findByRole("button", { name: "Add Another File" });
    await user.click(screen.getByRole("button", { name: "Check" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Suspicious Bangla text" }),
      { target: { value: query } },
    );
    await user.click(screen.getByRole("button", { name: "Check document" }));
    await screen.findByRole("dialog", { name: "Settings" });
    await user.type(screen.getByLabelText(/^API key/), "ui-fixture-token");
    await user.type(screen.getByLabelText(/^Model route ID/), "fixture/model");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Settings saved for this session.");
    expect(settings.key_configured).toBe(true);
    expect(JSON.stringify(localStorage)).not.toContain("ui-fixture-token");
    expect((screen.getByLabelText(/^API key/) as HTMLInputElement).value).toBe(
      "",
    );
    await user.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("generates a key-free preview and exposes actual candidate evidence for multiple sources", async () => {
    const { user } = mount();
    await screen.findByRole("heading", { name: /Find copied and reworded/ });
    await user.click(screen.getByRole("button", { name: "Library" }));
    await user.upload(
      screen.getByLabelText("Add source documents") as HTMLInputElement,
      [
        new File([query], "first.txt", { type: "text/plain" }),
        new File([query + "\n"], "second.txt", { type: "text/plain" }),
      ],
    );
    await screen.findByText("second.txt");
    await user.click(screen.getByRole("button", { name: "Check" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Suspicious Bangla text" }),
      { target: { value: query } },
    );
    await user.click(
      screen.getByRole("button", { name: /Try retrieval preview/ }),
    );
    await screen.findByRole("heading", { name: "Pasted text.txt" });
    expect(
      screen.getByText(
        "Retrieval evidence only — semantic verification was not performed.",
      ),
    ).toBeDefined();
    const generateCall = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => url === "/api/reports/generate");
    expect(JSON.parse(generateCall![1]!.body as string)).toEqual({
      text: query,
      preview_only: true,
    });
    expect(
      screen.getByRole("link", { name: "Download JSON" }).getAttribute("href"),
    ).toContain("/ui-fixture-report/download");
    await user.click(
      screen.getByRole("button", { name: "Sentence 1: Unverified" }),
    );
    expect(
      screen.getByRole("heading", { name: "Source evidence" }),
    ).toBeDefined();
    expect(screen.getAllByText("first.txt").length).toBeGreaterThan(0);
    expect(screen.getAllByText("second.txt").length).toBeGreaterThan(0);
    await user.selectOptions(screen.getByLabelText("Result"), "matched");
    await waitFor(() =>
      expect(
        screen.getByText("No evidence matches these filters."),
      ).toBeDefined(),
    );
  });
});
