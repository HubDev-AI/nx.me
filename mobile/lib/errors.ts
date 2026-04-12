import { ApiError } from './api';

export type FaceErrorZone = 'center' | 'top' | 'bottom' | 'left' | 'right' | 'whole';

export type AppError =
  | { kind: 'network'; message: string; cause?: unknown }
  | { kind: 'server'; message: string; status: number; cause?: unknown }
  | { kind: 'validation'; message: string; fieldErrors?: Record<string, string>; cause?: unknown }
  | { kind: 'auth'; message: string; cause?: unknown }
  | { kind: 'permission'; message: string; cause?: unknown }
  | { kind: 'rateLimit'; message: string; retryAfter?: number; cause?: unknown }
  | { kind: 'notFound'; message: string; cause?: unknown }
  | { kind: 'business'; message: string; errorCode: string; status: number; cause?: unknown }
  | { kind: 'faceAnalysis'; message: string; errorCode: string; zone?: FaceErrorZone; reason?: string; cause?: unknown }
  | { kind: 'featureDisabled'; message: string; feature?: string; cause?: unknown }
  | { kind: 'unknown'; message: string; cause?: unknown };

const FACE_ERROR_CODES = new Set([
  'face_not_detected',
  'face_too_close',
  'face_too_far',
  'lighting_too_dark',
  'lighting_too_bright',
  'face_obscured',
]);

interface BackendErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> | unknown[];
  };
}

function parseBody(body: string): BackendErrorBody | null {
  try {
    return JSON.parse(body) as BackendErrorBody;
  } catch {
    return null;
  }
}

export function parseApiError(err: unknown): AppError {
  // Network-level failures (fetch throws TypeError; aborts throw DOMException or TypeError)
  if (err instanceof Error) {
    const isAbort = err.name === 'AbortError' || /abort|timeout/i.test(err.message);
    const isNetwork =
      err instanceof TypeError &&
      /network request failed|failed to fetch|networkerror/i.test(err.message);
    if (isAbort || isNetwork) {
      return {
        kind: 'network',
        message: "You seem to be offline. We'll keep trying.",
        cause: err,
      };
    }
  }

  if (!(err instanceof ApiError)) {
    return {
      kind: 'unknown',
      message: 'Something unexpected happened. Give it another try.',
      cause: err,
    };
  }

  const body = parseBody(err.body);
  const code = body?.error?.code ?? '';
  const serverMsg = body?.error?.message;

  // Face-analysis errors take precedence regardless of status
  if (FACE_ERROR_CODES.has(code)) {
    const details = (body?.error?.details ?? {}) as { zone?: FaceErrorZone; reason?: string };
    return {
      kind: 'faceAnalysis',
      message: serverMsg ?? faceErrorCopy(code),
      errorCode: code,
      zone: details.zone,
      reason: details.reason,
      cause: err,
    };
  }

  switch (err.status) {
    case 401:
      return { kind: 'auth', message: "Your session expired. Let's sign you back in.", cause: err };
    case 403: {
      if (code === 'FEATURE_DISABLED') {
        const details = (body?.error?.details ?? {}) as { feature?: string };
        return {
          kind: 'featureDisabled',
          message: serverMsg ?? 'This feature is not currently available.',
          feature: details.feature,
          cause: err,
        };
      }
      return { kind: 'permission', message: "You don't have access to do that.", cause: err };
    }
    case 404:
      return { kind: 'notFound', message: "We couldn't find that.", cause: err };
    case 422: {
      const fieldErrors = extractFieldErrors(body);
      return {
        kind: 'validation',
        message: serverMsg ?? 'Some fields need a second look.',
        fieldErrors,
        cause: err,
      };
    }
    case 429: {
      const retryAfter = extractRetryAfter(body, err.headers);
      return {
        kind: 'rateLimit',
        message: retryAfter
          ? `Whoa, slow down — try again in ${retryAfter}s.`
          : 'Too many requests. Give it a moment.',
        retryAfter,
        cause: err,
      };
    }
    case 402:
      return {
        kind: 'business',
        message: serverMsg ?? "You're out of credits. Top up to continue?",
        errorCode: code || 'INSUFFICIENT_CREDITS',
        status: 402,
        cause: err,
      };
    case 409:
      return {
        kind: 'business',
        message: serverMsg ?? 'Looks like that already happened.',
        errorCode: code || 'CONFLICT',
        status: 409,
        cause: err,
      };
    default:
      if (err.status >= 500 && err.status < 600) {
        return {
          kind: 'server',
          message: 'Something went wrong on our end. Give it a moment.',
          status: err.status,
          cause: err,
        };
      }
      return {
        kind: 'unknown',
        message: serverMsg ?? 'Something unexpected happened. Give it another try.',
        cause: err,
      };
  }
}

function extractFieldErrors(body: BackendErrorBody | null): Record<string, string> | undefined {
  const details = body?.error?.details;
  if (!Array.isArray(details)) return undefined;
  const fieldErrors: Record<string, string> = {};
  for (const d of details) {
    if (!d || typeof d !== 'object') continue;
    // Pydantic shape: { loc: [...], msg, type }
    if ('loc' in d && 'msg' in d) {
      const { loc, msg } = d as { loc: unknown[]; msg: string };
      const field = loc
        .filter((x) => x !== 'body' && x !== 'query' && x !== 'path')
        .join('.');
      if (field && typeof msg === 'string') {
        fieldErrors[field] = msg;
      }
      continue;
    }
    // Legacy shape: { field, message }
    if ('field' in d && 'message' in d) {
      const { field, message } = d as { field: string; message: string };
      fieldErrors[field] = message;
    }
  }
  return Object.keys(fieldErrors).length ? fieldErrors : undefined;
}

function extractRetryAfter(
  body: BackendErrorBody | null,
  headers: Headers | null,
): number | undefined {
  // 1. HTTP Retry-After header (canonical)
  const headerValue = headers?.get('Retry-After');
  if (headerValue) {
    const asNumber = Number(headerValue);
    if (Number.isFinite(asNumber) && asNumber > 0) return asNumber;
    // HTTP date form: parse and compute diff
    const asDate = Date.parse(headerValue);
    if (!Number.isNaN(asDate)) {
      return Math.max(0, Math.round((asDate - Date.now()) / 1000));
    }
  }
  // 2. Body details.retry_after (number or ISO string)
  const details = body?.error?.details;
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    const v = (details as Record<string, unknown>).retry_after;
    if (typeof v === 'number' && v > 0) return v;
    if (typeof v === 'string') {
      const asDate = Date.parse(v);
      if (!Number.isNaN(asDate)) {
        return Math.max(0, Math.round((asDate - Date.now()) / 1000));
      }
    }
  }
  return undefined;
}

function faceErrorCopy(code: string): string {
  switch (code) {
    case 'face_not_detected':
      return "We couldn't find a face. Try a clear selfie.";
    case 'face_too_close':
      return 'Try pulling the camera back a bit.';
    case 'face_too_far':
      return 'Try bringing the camera a little closer.';
    case 'lighting_too_dark':
      return 'A brighter photo will give a better result.';
    case 'lighting_too_bright':
      return 'Try softer lighting.';
    case 'face_obscured':
      return 'Move hair or glasses away from your face and try again.';
    default:
      return 'Try a different photo.';
  }
}

/** Retry policy — drives `useAppQuery` / `useAppMutation` default retry. */
export function shouldRetry(err: AppError): boolean {
  return err.kind === 'network' || err.kind === 'server' || err.kind === 'rateLimit';
}
