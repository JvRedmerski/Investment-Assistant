/**
 * The single door to the backend (AGENTS.md rules 10 and 72).
 *
 * Everything the app fetches goes through `request`, which does four
 * things nothing else should have to repeat: prefix the base URL, attach
 * the bearer token, unwrap the `{"error":{"code","message"}}` envelope
 * into a typed error, and validate the response against a schema.
 *
 * ## Why every response is validated
 *
 * Rule 10 asks for `unknown` plus explicit validation rather than a cast.
 * A cast is a promise the compiler believes and nothing checks: rename a
 * field on the backend and the screen renders `undefined` where a number
 * should be, silently. `zod` turns that into an error at the boundary,
 * with the field name in it.
 *
 * This is the same argument the backend makes about external data being
 * hostile (rule 19). The API is external to this codebase too, and the
 * frontend is the last place a wrong number can be caught before an
 * investor reads it as a fact about their money.
 *
 * ## Money stays a string until it is formatted
 *
 * The backend sends `Decimal` as a JSON string precisely so it does not
 * pass through a binary float. Parsing it into a `number` here would
 * throw that away in the one hop it was protected across, so the schemas
 * keep money as `string` and `lib/format.ts` is what turns it into
 * something a person reads.
 */

import { z } from 'zod';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const TOKEN_KEY = 'ia.token';

/** The backend's error envelope, exactly as rule 72 defines it. */
const errorEnvelope = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});

/**
 * A failed request, carrying the backend's own error code.
 *
 * The `code` is what callers branch on — `ASSET_NOT_FOUND`,
 * `BENCHMARK_NOT_FOUND`, `INSUFFICIENT_POSITION` — rather than parsing
 * the message, which is prose and may change.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Whether the session is gone and the user has to sign in again. */
  get isUnauthorised(): boolean {
    return this.status === 401;
  }
}

/**
 * A response whose shape did not match the contract.
 *
 * Deliberately distinct from `ApiError`: one means the backend said no,
 * the other means the backend and this client disagree about what the
 * answer looks like. They call for different fixes and should never be
 * reported as the same thing.
 */
export class ContractError extends Error {
  constructor(
    readonly path: string,
    readonly detail: string,
  ) {
    super(`Resposta inesperada de ${path}: ${detail}`);
    this.name = 'ContractError';
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // A browser with site data blocked still has to render the login
    // screen rather than crash on the way to it.
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token === null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Session lasts the tab instead of the browser. Worth degrading to,
    // not worth failing the sign-in for.
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  params?: Record<string, string | number | undefined | null>;
  /** Send without the bearer token — only register and login do. */
  anonymous?: boolean;
}

/**
 * Call the API and return a value the schema vouches for.
 *
 * Throws `ApiError` when the backend refuses and `ContractError` when it
 * answers with something this client cannot read.
 */
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, params, anonymous = false } = options;

  const url = new URL(`${API_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = anonymous ? null : getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // A network failure is not an API error: there is no code and no
    // message from the backend, because it was never reached.
    throw new ApiError(0, 'NETWORK_ERROR', 'Não foi possível falar com o servidor.');
  }

  if (response.status === 204) {
    return schema.parse(undefined);
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const envelope = errorEnvelope.safeParse(payload);
    if (envelope.success) {
      throw new ApiError(
        response.status,
        envelope.data.error.code,
        envelope.data.error.message,
      );
    }
    throw new ApiError(
      response.status,
      'HTTP_ERROR',
      `O servidor respondeu ${response.status}.`,
    );
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ContractError(path, parsed.error.issues[0]?.message ?? 'formato inválido');
  }
  return parsed.data;
}
