import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";

export const runtime = "nodejs";
const execute = promisify(execFile);

export async function POST(request: Request) {
  let directory: string | undefined;
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 1_000_000) return Response.json({ error: "The document exceeds the 1 MB limit." }, { status: 413 });
    const data = JSON.parse(raw);
    if (!data || typeof data.markdown !== "string" || !data.markdown.trim()) throw new Error("Add some Markdown before generating a PDF.");
    const { title = "", author = "", pageSize = "letter", typeface = "sans", startOnRight = true, duplex = true, grayscale = true, midpoint = 1.08 } = data;
    if (typeof title !== "string" || typeof author !== "string" || title.length > 1000 || author.length > 500) throw new Error("Title or author is invalid or too long.");
    if (!["letter", "a4", "half-letter"].includes(pageSize) || !["sans", "serif"].includes(typeface)) throw new Error("Choose a supported paper size and typeface.");
    if ([startOnRight, duplex, grayscale].some(value => typeof value !== "boolean") || typeof midpoint !== "number" || !Number.isFinite(midpoint) || midpoint < 0.85 || midpoint > 1.35) throw new Error("Invalid document settings.");
    const root = process.cwd();
    const python = process.env.JOURNAL_PYTHON || ".venv/bin/python";
    directory = await mkdtemp(path.join(tmpdir(), "journal-render-"));
    const input = path.join(directory, "article.md");
    const output = path.join(directory, "article.pdf");
    await writeFile(input, data.markdown, "utf8");
    const { stdout } = await execute(python, [
      path.join(root, "markdown_columns.py"), input, output, "--web",
      `--title=${title}`, `--author=${author}`, `--page-size=${pageSize}`, `--typeface=${typeface}`, `--midpoint=${midpoint}`,
      startOnRight ? "--start-on-right" : "--no-start-on-right",
      duplex ? "--duplex" : "--no-duplex", grayscale ? "--grayscale" : "--no-grayscale",
    ], { cwd: root, timeout: 120_000, maxBuffer: 1_000_000, signal: request.signal });
    const result = JSON.parse(stdout.trim());
    const pdf = await readFile(output);
    return new Response(new Uint8Array(pdf), { headers: {
      "content-type": "application/pdf", "content-disposition": 'inline; filename="journal.pdf"',
      "cache-control": "no-store", "x-page-count": String(result.pages),
    } });
  } catch (caught) {
    const error = caught as Error & { stderr?: string; code?: string; killed?: boolean };
    let message = error.message || "Could not render the PDF.";
    if (error.stderr?.includes("ModuleNotFoundError") || error.code === "ENOENT") {
      message = "The PDF renderer needs Python dependencies. Run .venv/bin/pip install -r requirements.txt, or configure JOURNAL_PYTHON.";
    } else if (error.killed) message = "The PDF took too long to render. Try fewer or smaller figures.";
    else if (error.stderr) message = error.stderr.trim().split("\n").at(-1) || "Could not render the PDF.";
    return Response.json({ error: message }, { status: 400 });
  } finally {
    if (directory) await rm(directory, { recursive: true, force: true });
  }
}
