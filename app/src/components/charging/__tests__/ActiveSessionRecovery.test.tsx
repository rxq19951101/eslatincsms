import React from 'react';
import { AppState } from 'react-native';
import { act, render, waitFor } from '@testing-library/react-native';
import ActiveSessionRecovery from '../ActiveSessionRecovery';
import { restoreActiveSession } from '../../../store/slices/chargingSlice';
import { navigationRef } from '../../../navigation/navigationRef';

const mockDispatch = jest.fn();
const mockState = {
  auth: {
    isAuthenticated: true,
    isInitialized: true,
    user: { id: 'user-1' },
  },
  charging: {
    recoveryChecked: true,
    activeSession: { id: 'session-1' },
  },
};

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (value: typeof mockState) => unknown) => selector(mockState),
}));

jest.mock('../../../store/slices/chargingSlice', () => ({
  restoreActiveSession: jest.fn(() => ({ type: 'charging/restoreActive' })),
}));

jest.mock('../../../navigation/navigationRef', () => ({
  navigationRef: {
    isReady: jest.fn(() => true),
    getCurrentRoute: jest.fn(() => ({ name: 'MainTabs' })),
    navigate: jest.fn(),
  },
}));

describe('ActiveSessionRecovery', () => {
  let onAppStateChange: ((state: 'active' | 'background' | 'inactive' | 'unknown' | 'extension') => void) | undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    mockDispatch.mockResolvedValue({
      type: 'charging/restoreActive/fulfilled',
      payload: mockState.charging.activeSession,
      meta: { requestStatus: 'fulfilled' },
    });
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => {
      onAppStateChange = listener;
      return { remove: jest.fn() };
    });
  });

  it('does one read-only recovery after login and opens the ongoing session', async () => {
    const screen = render(<ActiveSessionRecovery />);
    screen.rerender(<ActiveSessionRecovery />);

    await waitFor(() => {
      expect(restoreActiveSession).toHaveBeenCalledTimes(1);
      expect(mockDispatch).toHaveBeenCalledTimes(1);
      expect(navigationRef.navigate).toHaveBeenCalledWith('ChargingProcess', { sessionId: 'session-1' });
    });
  });

  it('refreshes once when the authenticated app returns to the foreground without navigating again', async () => {
    render(<ActiveSessionRecovery />);
    await waitFor(() => expect(restoreActiveSession).toHaveBeenCalledTimes(1));

    act(() => {
      onAppStateChange?.('background');
      onAppStateChange?.('active');
    });

    await waitFor(() => expect(restoreActiveSession).toHaveBeenCalledTimes(2));
    expect(navigationRef.navigate).toHaveBeenCalledTimes(1);
  });
});
