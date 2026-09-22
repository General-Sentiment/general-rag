import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export const runtime = "nodejs";

const MAX_IMAGE_BYTES = 12_000_000;

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
  if (!['http:', 'https:'].includes(url.protocol) || isPrivateHost(url.hostname)) {
    throw new Error("Only public images can be loaded.");
  }
  const addresses = await lookup(url.hostname, { all: true, verbatim: true });
  if (!addresses.length || addresses.some(({ address }) => isPrivateHost(address))) {
    throw new Error("That image address is not available.");
  }
}

async function fetchImage(initialUrl: URL, signal: AbortSignal) {
  let url = initialUrl;
  for (let redirect = 0; redirect < 5; redirect += 1) {
    await assertPublicUrl(url);
    const response = await fetch(url, {
      redirect: "manual",
      signal,
      headers: {
        accept: "image/avif,image/webp,image/png,image/jpeg,image/gif,image/svg+xml,image/*;q=0.8",
        "user-agent": "JournalPrint/0.1 (+image proxy)",
      },
    });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (!location) throw new Error("The image redirected without a destination.");
      url = new URL(location, url);
      continue;
    }
    return response;
  }
  throw new Error("The image redirected too many times.");
}

export async function GET(request: Request) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const source = new URL(request.url).searchParams.get("url");
    if (!source) return Response.json({ error: "An image URL is required." }, { status: 400 });

    const response = await fetchImage(new URL(source), controller.signal);
    if (!response.ok) throw new Error(`The image returned ${response.status}.`);

    const contentType = response.headers.get("content-type")?.split(";")[0] ?? "";
    if (!contentType.startsWith("image/")) throw new Error("That URL did not return an image.");

    const declaredLength = Number(response.headers.get("content-length") ?? 0);
    if (declaredLength > MAX_IMAGE_BYTES) throw new Error("The image is too large.");

    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > MAX_IMAGE_BYTES) throw new Error("The image is too large.");

    return new Response(bytes, {
      headers: {
        "cache-control": "public, max-age=86400, stale-while-revalidate=604800",
        "content-length": String(bytes.byteLength),
        "content-type": contentType,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not load the image.";
    return Response.json({ error: message }, { status: 400 });
  } finally {
    clearTimeout(timeout);
  }
}
