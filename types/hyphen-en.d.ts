declare module "hyphen/en" {
  type HyphenationOptions = {
    debug?: boolean;
    exceptions?: string[];
    hyphenChar?: string;
    minWordLength?: number;
  };

  export function hyphenateSync(
    text: string,
    options?: Readonly<HyphenationOptions>,
  ): string;
}
