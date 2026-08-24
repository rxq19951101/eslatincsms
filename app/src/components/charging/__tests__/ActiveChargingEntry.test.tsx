import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import ActiveChargingEntry from '../ActiveChargingEntry';
import { navigationRef } from '../../../navigation/navigationRef';

let mockActiveSession: { id: string; ocpp_identity: string } | null = {
  id: 'session-42',
  ocpp_identity: 'CP-PUBLIC-42',
};

jest.mock('../../../hooks/useRedux', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) => selector({ charging: { activeSession: mockActiveSession } }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({
    t: {
      common: { unknown: 'Unknown' },
      charging: { activeSessionEntry: 'Return to active charging' },
    },
  }),
}));

jest.mock('../../../navigation/navigationRef', () => ({
  navigationRef: {
    isReady: jest.fn(() => true),
    navigate: jest.fn(),
  },
}));

jest.mock('../../ui/Icon', () => () => null);

describe('ActiveChargingEntry', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockActiveSession = { id: 'session-42', ocpp_identity: 'CP-PUBLIC-42' };
  });

  it('opens the active charging process by session id', () => {
    const screen = render(<ActiveChargingEntry />);

    expect(screen.getByText('CP-PUBLIC-42')).toBeTruthy();
    fireEvent.press(screen.getByTestId('active-charging-entry'));

    expect(navigationRef.navigate).toHaveBeenCalledWith('ChargingProcess', {
      sessionId: 'session-42',
    });
  });

  it('is hidden when there is no active session', () => {
    mockActiveSession = null;
    const screen = render(<ActiveChargingEntry />);

    expect(screen.queryByTestId('active-charging-entry')).toBeNull();
  });
});
