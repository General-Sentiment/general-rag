import { Defuddle } from "defuddle/node";
import { parseHTML } from "linkedom";
import { NextResponse } from "next/server";
import { isIP } from "node:net";
import { lookup } from "node:dns/promises";

export const runtime = "nodejs";

function isPrivateHost(hostname: string) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (host === "localhost" || host.endsWith(".local") || host.endsWith(".internal")) return true;
  const ipVersion = isIP(host);
  if (ipVersion === 4) {
    const [a, b] = host.split(".").map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }
  if (ipVersion === 6) {
    return host === "::1" || host.startsWith("fc") || host.startsWith("fd") || host.startsWith("fe80:");
  }
  return false;
}

async function assertPublicUrl(url: URL) {
  if (!["http:", "https:"].includes(url.protocol) || isPrivateHost(url.hostname)) {
    throw new Error("Enter a public http or https URL.");
  }
  const addresses = await lookup(url.hostname, { all: true, verbatim: true });
  if (!addresses.length || addresses.some(({ address }) => isPrivateHost(address))) {
    throw new Error("That address cannot be imported.");
  }
}

async function fetchArticle(initialUrl: URL, signal: AbortSignal) {
  let url = initialUrl;
  for (let redirect = 0; redirect < 5; redirect += 1) {
    await assertPublicUrl(url);
    const response = await fetch(url, {
      redirect: "manual",
      signal,
      headers: { "user-agent": "JournalPrint/0.1 (+article reader)" },
    });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (!location) throw new Error("The page redirected without a destination.");
      url = new URL(location, url);
      continue;
    }
    return { response, url };
  }
  throw new Error("The page redirected too many times.");
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { url?: string };
    const url = new URL(body.url ?? "");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12_000);
    const { response, url: finalUrl } = await fetchArticle(url, controller.signal);
    clearTimeout(timeout);

    if (!response.ok) throw new Error(`The page returned ${response.status}.`);
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
      throw new Error("That URL does not appear to be an HTML article.");
    }
    const length = Number(response.headers.get("content-length") ?? 0);
    if (length > 5_000_000) throw new Error("The page is too large to import.");
    const html = await response.text();
    if (html.length > 5_000_000) throw new Error("The page is too large to import.");

    const { document } = parseHTML(html);
    const result = await Defuddle(document, finalUrl.href, {
      markdown: true,
      separateMarkdown: true,
    });

    return NextResponse.json({
      title: result.title ?? "Untitled",
      author: result.author ?? "",
      published: result.published ?? "",
      markdown: result.contentMarkdown ?? result.content ?? "",
      source: finalUrl.href,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to import this page.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
