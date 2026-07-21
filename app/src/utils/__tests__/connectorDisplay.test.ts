import { connectorStandardLabel } from '../connectorDisplay';

describe('connectorStandardLabel', () => {
  it('formats public connector standards consistently', () => {
    expect(connectorStandardLabel('TYPE_2')).toBe('Type 2');
    expect(connectorStandardLabel('CCS_2')).toBe('CCS2');
    expect(connectorStandardLabel('CHADEMO')).toBe('CHAdeMO');
  });

  it('does not expose UNKNOWN as a user-facing model', () => {
    expect(connectorStandardLabel('UNKNOWN')).toBe('');
  });
});
