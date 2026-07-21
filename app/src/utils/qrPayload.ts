export type ParsedQrPayload = { qrToken: string };

/** Accept only the public scan formats emitted by the backend QR service. */
export function parseQrPayload(raw: string): ParsedQrPayload | null {
  const value = (raw || '').trim();
  if (!value) return null;

  if (value.startsWith('{') && value.endsWith('}')) {
    try {
      const parsed = JSON.parse(value) as { qrToken?: unknown; qr_token?: unknown };
      const token = parsed.qrToken ?? parsed.qr_token;
      if (typeof token === 'string' && token.trim()) return { qrToken: token.trim() };
    } catch {
      return null;
    }
  }

  if (value.toLowerCase().startsWith('qr:')) {
    const token = value.slice(3).trim();
    if (token) return { qrToken: token };
  }

  return null;
}
