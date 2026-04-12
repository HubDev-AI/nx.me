import { ApiError } from './api';
import { parseApiError, shouldRetry } from './errors';

describe('parseApiError', () => {
  it('maps network errors (TypeError from fetch)', () => {
    const err = new TypeError('Network request failed');
    const result = parseApiError(err);
    expect(result.kind).toBe('network');
    expect(result.message).toContain('offline');
  });

  it('maps 422 to validation', () => {
    const err = new ApiError(
      422,
      JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: 'Invalid', details: [] } }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('validation');
  });

  it('maps 401 to auth', () => {
    const err = new ApiError(401, '{"error":{"code":"UNAUTHORIZED","message":"nope"}}', '/v1/x');
    expect(parseApiError(err).kind).toBe('auth');
  });

  it('maps 429 with retry_after', () => {
    const err = new ApiError(
      429,
      JSON.stringify({ error: { code: 'RATE_LIMIT_EXCEEDED', message: 'slow', details: { retry_after: 30 } } }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('rateLimit');
    if (result.kind === 'rateLimit') {
      expect(result.retryAfter).toBe(30);
    }
  });

  it('maps 402 to business (insufficient credits)', () => {
    const err = new ApiError(402, '{"error":{"code":"INSUFFICIENT_CREDITS","message":"buy more"}}', '/v1/x');
    const result = parseApiError(err);
    expect(result.kind).toBe('business');
  });

  it('maps 500 to server', () => {
    const err = new ApiError(500, '{"error":{"code":"INTERNAL_ERROR","message":"oops"}}', '/v1/x');
    expect(parseApiError(err).kind).toBe('server');
  });

  it('maps face-analysis error code to faceAnalysis', () => {
    const err = new ApiError(
      422,
      JSON.stringify({
        error: { code: 'face_too_close', message: 'too close', details: { zone: 'center', reason: '>80%' } },
      }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('faceAnalysis');
    if (result.kind === 'faceAnalysis') {
      expect(result.zone).toBe('center');
      expect(result.errorCode).toBe('face_too_close');
    }
  });

  it('falls back to unknown for unexpected errors', () => {
    const result = parseApiError('weird string');
    expect(result.kind).toBe('unknown');
  });
});

describe('parseApiError — backend shapes', () => {
  it('extracts fieldErrors from Pydantic 422 shape', () => {
    const err = new ApiError(
      422,
      JSON.stringify({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid',
          details: [
            { loc: ['body', 'email'], msg: 'field required', type: 'missing' },
            { loc: ['body', 'password'], msg: 'too short', type: 'min_length' },
          ],
        },
      }),
      '/v1/x',
    );
    const result = parseApiError(err);
    if (result.kind === 'validation') {
      expect(result.fieldErrors).toEqual({ email: 'field required', password: 'too short' });
    } else {
      throw new Error('expected validation kind');
    }
  });

  it('reads retryAfter from Retry-After header', () => {
    const headers = new Headers({ 'Retry-After': '60' });
    const err = new ApiError(429, '{"error":{"code":"x","message":"y"}}', '/v1/x', headers);
    const result = parseApiError(err);
    if (result.kind === 'rateLimit') {
      expect(result.retryAfter).toBe(60);
    } else {
      throw new Error('expected rateLimit kind');
    }
  });

  it('handles empty body on 422', () => {
    const err = new ApiError(422, '', '/v1/x');
    expect(parseApiError(err).kind).toBe('validation');
  });

  it('falls back to unknown for unhandled status', () => {
    const err = new ApiError(418, '{"error":{"code":"teapot","message":"brew"}}', '/v1/x');
    expect(parseApiError(err).kind).toBe('unknown');
  });

  it('classifies AbortError as network', () => {
    const err = new Error('The operation was aborted.');
    err.name = 'AbortError';
    expect(parseApiError(err).kind).toBe('network');
  });
});

describe('shouldRetry', () => {
  it('retries network, server, rateLimit', () => {
    expect(shouldRetry({ kind: 'network', message: '' })).toBe(true);
    expect(shouldRetry({ kind: 'server', message: '', status: 500 })).toBe(true);
    expect(shouldRetry({ kind: 'rateLimit', message: '' })).toBe(true);
  });

  it('does not retry auth, validation, permission, business, faceAnalysis, notFound, unknown', () => {
    expect(shouldRetry({ kind: 'auth', message: '' })).toBe(false);
    expect(shouldRetry({ kind: 'validation', message: '' })).toBe(false);
    expect(shouldRetry({ kind: 'permission', message: '' })).toBe(false);
    expect(shouldRetry({ kind: 'business', message: '', errorCode: '', status: 402 })).toBe(false);
    expect(shouldRetry({ kind: 'faceAnalysis', message: '', errorCode: 'x' })).toBe(false);
    expect(shouldRetry({ kind: 'notFound', message: '' })).toBe(false);
    expect(shouldRetry({ kind: 'unknown', message: '' })).toBe(false);
  });
});
