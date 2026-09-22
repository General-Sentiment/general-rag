"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import "pdfjs-dist/web/pdf_viewer.css";

function PdfPage({ document, number }: { document: PDFDocumentProxy; number: number }) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); }
    }, { rootMargin: "600px" });
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let disposed = false;
    let renderTask: { cancel(): void } | undefined;
    let textLayer: { cancel(): void } | undefined;
    async function render() {
      try {
        const page = await document.getPage(number);
        const pdfjs = await import("pdfjs-dist");
        if (disposed || !canvas.current || !text.current || !host.current) return;
        const viewport = page.getViewport({ scale: 1.5 });
        host.current.style.aspectRatio = `${viewport.width} / ${viewport.height}`;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.current.width = Math.ceil(viewport.width * ratio);
        canvas.current.height = Math.ceil(viewport.height * ratio);
        renderTask = page.render({ canvas: canvas.current, viewport, transform: [ratio, 0, 0, ratio, 0, 0] });
        await (renderTask as ReturnType<typeof page.render>).promise;
        if (disposed) return;
        const content = await page.getTextContent();
        if (disposed || !text.current) return;
        text.current.replaceChildren();
        // The text layer uses PDF coordinates; the entire surface scales together.
        text.current.style.width = `${viewport.width}px`;
        text.current.style.height = `${viewport.height}px`;
        text.current.style.setProperty("--scale-factor", String(viewport.scale));
        const layer = new pdfjs.TextLayer({ textContentSource: content, container: text.current, viewport });
        textLayer = layer;
        await layer.render();
      } catch (caught) {
        if (!disposed) setError(caught instanceof Error ? caught.message : "Could not display this PDF page.");
      }
    }
    void render();
    return () => { disposed = true; renderTask?.cancel(); textLayer?.cancel(); };
  }, [document, number, visible]);
  // Resize only the overlay's visual scale, never the PDF's layout.
  useEffect(() => {
    const observer = new ResizeObserver(() => {
      if (host.current && text.current) {
        const width = parseFloat(text.current.style.width);
        if (width) text.current.style.transform = `scale(${host.current.clientWidth / width})`;
      }
    });
    if (host.current) observer.observe(host.current);
    if (text.current) observer.observe(text.current);
    return () => observer.disconnect();
  }, []);
  return <div className="pdf-page" ref={host} aria-label={`Page ${number}`}>
    <canvas ref={canvas} />
    <div className="textLayer" ref={text} />
    {error && <p role="alert">{error}</p>}
  </div>;
}

export function PdfPreview({ url }: { url: string }) {
  const [document, setDocument] = useState<PDFDocumentProxy>();
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    let task: { destroy(): Promise<void> } | undefined;
    void (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        if (disposed) return;
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
        const loading = pdfjs.getDocument({ url });
        task = loading;
        const next = await loading.promise;
        if (!disposed) setDocument(next);
      } catch (caught) { if (!disposed) setError(caught instanceof Error ? caught.message : "Could not display the PDF."); }
    })();
    return () => { disposed = true; void task?.destroy(); };
  }, [url]);
  return <div className="pdf-preview">
    {error && <p role="alert">{error} Use Download PDF to open it in your PDF reader.</p>}
    {!document && !error && <p>Loading PDF…</p>}
    {document && Array.from({ length: document.numPages }, (_, index) => <PdfPage key={index} document={document} number={index + 1} />)}
  </div>;
}
