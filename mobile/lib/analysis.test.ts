import { getJobFailureMessage } from './analysis';

describe('getJobFailureMessage', () => {
  it('prefers server-provided user_guidance when present', () => {
    const msg = getJobFailureMessage(
      'IDENTITY_PRESERVATION_FAILED',
      'Try a clearer photo or a less dramatic style.',
    );
    expect(msg).toBe('Try a clearer photo or a less dramatic style.');
  });

  it('maps IDENTITY_PRESERVATION_FAILED to readable copy', () => {
    const msg = getJobFailureMessage('IDENTITY_PRESERVATION_FAILED', null);
    expect(msg).not.toContain('IDENTITY');
    expect(msg).not.toContain('_');
    expect(msg.toLowerCase()).toContain('likeness');
  });

  it('maps NSFW_CONTENT_DETECTED to safety-filter copy', () => {
    const msg = getJobFailureMessage('NSFW_CONTENT_DETECTED', null);
    expect(msg.toLowerCase()).toContain('safety');
  });

  it('maps GENERATION_TIMEOUT and reassures about credits', () => {
    const msg = getJobFailureMessage('GENERATION_TIMEOUT', null);
    expect(msg.toLowerCase()).toContain('credit');
  });

  it('maps PROVIDER_ERROR and reassures about credits', () => {
    const msg = getJobFailureMessage('PROVIDER_ERROR', null);
    expect(msg.toLowerCase()).toContain('credit');
  });

  it('falls back to generic copy for unknown codes', () => {
    const msg = getJobFailureMessage('SOMETHING_NEW_NOT_YET_MAPPED', null);
    expect(msg).toBe('Generation failed. Please try again.');
  });

  it('falls back to generic copy for null / undefined code', () => {
    expect(getJobFailureMessage(null, null)).toBe(
      'Generation failed. Please try again.',
    );
    expect(getJobFailureMessage(undefined, undefined)).toBe(
      'Generation failed. Please try again.',
    );
  });

  it('ignores blank server guidance and uses the map', () => {
    const msg = getJobFailureMessage('IDENTITY_PRESERVATION_FAILED', '   ');
    expect(msg.toLowerCase()).toContain('likeness');
  });

  it('uses server guidance even when the code is unknown', () => {
    const msg = getJobFailureMessage(
      'SOME_FUTURE_CODE_NOT_MAPPED',
      'Specific hint from the backend.',
    );
    expect(msg).toBe('Specific hint from the backend.');
  });
});
