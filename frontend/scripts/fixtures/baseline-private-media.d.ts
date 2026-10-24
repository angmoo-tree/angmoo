/** Only the isolated regression bundle resolves this alias to a saved Git source. */
declare module "baseline-private-media" {
  export function usePrivateMediaUrl(source: string | null | undefined): string | null;
}
