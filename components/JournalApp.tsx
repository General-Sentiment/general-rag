"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { normalizeArticleUrl } from "@/lib/article-url";
import { PdfPreview } from "./PdfPreview";

type PageSize = "letter" | "a4" | "half-letter";
type Typeface = "sans" | "serif";
const PAPER_LABELS: Record<PageSize, string> = {
  letter: "Letter — 8.5 × 11 in", a4: "A4 — 210 × 297 mm", "half-letter": "Half Letter — 5.5 × 8.5 in",
};

export function JournalApp() {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [url, setUrl] = useState("");
  const [typeface, setTypeface] = useState<Typeface>("sans");
  const [pageSize, setPageSize] = useState<PageSize>("letter");
  const [startOnRight, setStartOnRight] = useState(true);
  const [duplex, setDuplex] = useState(true);
  const [grayscale, setGrayscale] = useState(true);
  const [midpoint, setMidpoint] = useState(1.08);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [pdf, setPdf] = useState<{ url: string; pages: number; key: string; title: string }>();
  const activeRequest = useRef<AbortController | null>(null);
  const pdfUrl = useRef<string | null>(null);
  const settings = { title, author, markdown, pageSize, typeface, startOnRight, duplex, grayscale, midpoint };
  const currentKey = JSON.stringify(settings);
  const stale = Boolean(pdf && pdf.key !== currentKey);

  useEffect(() => () => {
    activeRequest.current?.abort();
    if (pdfUrl.current) URL.revokeObjectURL(pdfUrl.current);
  }, []);

  async function generatePreview(overrides?: { title: string; author: string; markdown: string }) {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setSaving(true); setSaveError("");
    const payload = { ...settings, ...overrides };
    try {
      const response = await fetch("/api/render", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal });
      if (!response.ok) throw new Error((await response.json()).error || "Could not generate the PDF.");
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      const nextUrl = URL.createObjectURL(blob);
      const previousUrl = pdfUrl.current;
      pdfUrl.current = nextUrl;
      setPdf({ url: nextUrl, pages: Number(response.headers.get("x-page-count")), key: JSON.stringify(payload), title: payload.title });
      if (previousUrl) URL.revokeObjectURL(previousUrl);
    } catch (caught) {
      if (!controller.signal.aborted) setSaveError(caught instanceof Error ? caught.message : "Could not generate the PDF.");
    } finally {
      if (activeRequest.current === controller) setSaving(false);
    }
  }

  async function importUrl(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const normalizedUrl = normalizeArticleUrl(url);
      setUrl(normalizedUrl);
      const response = await fetch("/api/extract", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url: normalizedUrl }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not import that page.");
      const document = { title: result.title || "", author: result.author || "", markdown: result.markdown };
      setTitle(document.title); setAuthor(document.author); setMarkdown(document.markdown);
      await generatePreview(document);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not import that page."); }
    finally { setLoading(false); }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <aside className="controls" aria-label="Document controls">
          <div className="controls-scroll">
            <div className="sidebar-status" aria-label="Preview status" aria-live="polite">
              <span>{saving ? "Generating PDF…" : pdf ? `${pdf.pages} pages${stale ? " · needs update" : ""}` : "No PDF yet"}</span>
              <span>{PAPER_LABELS[pageSize]}</span>
            </div>
            <form className="url-form" onSubmit={importUrl}>
              <label htmlFor="article-url">Article URL</label>
              <div className="inline-field">
                <input id="article-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://" required />
                <button type="submit" disabled={loading}>{loading ? "Importing" : "Import"}</button>
              </div>
              {error && <p className="error" role="alert">{error}</p>}
            </form>

            <div className="metadata-fields">
              <label htmlFor="document-title">Title</label>
              <input
                id="document-title"
                type="text"
                value={title}
                onInput={(event) => setTitle(event.currentTarget.value)}
              />

              <label htmlFor="document-author">Author</label>
              <input
                id="document-author"
                type="text"
                value={author}
                onInput={(event) => setAuthor(event.currentTarget.value)}
              />
            </div>

            <label htmlFor="markdown">Markdown</label>
            <textarea
              id="markdown"
              value={markdown}
              onInput={(event) => setMarkdown(event.currentTarget.value)}
              spellCheck="true"
            />

            <fieldset>
              <legend>Typeface</legend>
              <div className="segmented">
                <button type="button" aria-pressed={typeface === "sans"} onClick={() => setTypeface("sans")}>Sans</button>
                <button type="button" aria-pressed={typeface === "serif"} onClick={() => setTypeface("serif")}>Serif</button>
              </div>
            </fieldset>

            <label htmlFor="page-size">Page size</label>
            <select id="page-size" value={pageSize} onChange={(event) => setPageSize(event.target.value as PageSize)}>
              {Object.entries(PAPER_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>

            <label className="check-row"><input type="checkbox" checked={startOnRight} onChange={(event) => setStartOnRight(event.target.checked)} /> Start text in right column</label>
            <label className="check-row"><input type="checkbox" checked={duplex} onChange={(event) => setDuplex(event.target.checked)} /> Double-sided</label>
            {duplex && <p className="note">Print the PDF double-sided, flip on the long edge, and use actual size with matching paper.</p>}

            <label className="check-row"><input type="checkbox" checked={grayscale} onChange={(event) => setGrayscale(event.target.checked)} /> Grayscale images</label>
            {grayscale && (
              <div className="range-field">
                <label htmlFor="midpoint">Image midpoint <output>{midpoint.toFixed(2)}</output></label>
                <input id="midpoint" type="range" min="0.85" max="1.35" step="0.01" value={midpoint} onChange={(event) => setMidpoint(Number(event.target.value))} />
                <span>Higher values lift the midtones for laser printing.</span>
              </div>
            )}
          </div>
          <div className="print-actions">
            {saveError && <p className="error" role="alert">{saveError}</p>}
            <button className="generate-button" type="button" onClick={() => void generatePreview()} disabled={saving || loading || !markdown.trim()}>
              {saving ? "Generating PDF…" : "Generate PDF"}
            </button>
            {pdf && <a className="print-button" href={pdf.url} download={`${pdf.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "journal"}.pdf`}>Download PDF{stale ? " (previous version)" : ""}</a>}
          </div>
        </aside>
        <section className="preview-region" aria-label="PDF preview" aria-busy={saving}>
          {pdf ? <PdfPreview key={pdf.url} url={pdf.url} /> : <div className="preview-empty">Paste Markdown or import an article, then generate your PDF.</div>}
        </section>
      </section>
    </main>
  );
}
