const MARKDOWN_LINK = /^\[[^\]]*\]\((https?:\/\/[^)]+)\)$/i;
const INVISIBLE_CHARACTERS = /[\u200B-\u200D\u2060\uFEFF]/g;

export function normalizeArticleUrl(input: string) {
  let candidate = input.trim().replace(INVISIBLE_CHARACTERS, "");
  const markdownLink = candidate.match(MARKDOWN_LINK);
  if (markdownLink) candidate = markdownLink[1];

  // URL fields are commonly populated from formatted text that inserts a
  // space after the scheme or a soft line break in the middle of the URL.
  candidate = candidate.replace(/\s+/g, "");
  if (!/^[a-z][a-z\d+.-]*:\/\//i.test(candidate)) candidate = `https://${candidate}`;

  try {
    return new URL(candidate).href;
  } catch {
    throw new Error("Enter a valid public article URL.");
  }
}
