export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null,
    readonly params: Record<string, unknown> = {}, readonly retryAfter: string | null = null) {
    super(message);
    this.name = "ApiRequestError";
  }
}

