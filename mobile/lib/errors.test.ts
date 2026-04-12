import { ApiError } from './api';
import { parseApiError } from './errors';

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
