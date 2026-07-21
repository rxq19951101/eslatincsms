import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import QrPayloadCopy, { publicScanPayload } from '../QrPayloadCopy';

describe('QrPayloadCopy', () => {
  it('exposes only the public server token scan payload and copies it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(<QrPayloadCopy qrToken="server-generated-token" connectorId={1} />);
    expect(screen.getByTestId('admin-qr-payload-1')).toHaveValue('qr:server-generated-token');
    expect(screen.queryByText(/charge_point_id|tenant_id|internal/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('admin-qr-copy-payload-1'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('qr:server-generated-token'));
  });

  it('does not render a payload entry before the backend returns a token', () => {
    const { container } = render(<QrPayloadCopy qrToken={null} connectorId={1} />);
    expect(container).toBeEmptyDOMElement();
    expect(publicScanPayload('token')).toBe('qr:token');
  });
});
