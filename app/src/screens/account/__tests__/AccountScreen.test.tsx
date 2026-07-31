import React from 'react';
import { act, fireEvent, render, waitFor, within } from '@testing-library/react-native';

import { en as mockEn } from '../../../i18n/en';
import AccountScreen from '../AccountScreen';
import { logout } from '../../../store/slices/authSlice';

const mockNavigate = jest.fn();
const mockReplace = jest.fn();
const mockDispatch = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: mockNavigate,
    replace: mockReplace,
  }),
}));

jest.mock('../../../hooks/useRedux', () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      auth: {
        user: {
          id: 'user-1',
          full_name: 'Ada Lovelace',
          email: 'ada@example.com',
        },
        isLoading: false,
      },
    }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn, locale: 'en' }),
}));

jest.mock('../../../store/slices/authSlice', () => ({
  logout: jest.fn(() => ({ type: 'auth/logout' })),
}));

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return () => <View />;
});

describe('AccountScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDispatch.mockResolvedValue(undefined);
  });

  it('renders a scrollable, grouped account root without account deletion', () => {
    const screen = render(<AccountScreen />);

    expect(screen.getByTestId('account-scroll-view')).toBeTruthy();
    expect(screen.getByText(mockEn.account.chargingAndPayments)).toBeTruthy();
    expect(screen.getByText(mockEn.account.preferences)).toBeTruthy();
    expect(screen.getByText(mockEn.account.supportAndLegal)).toBeTruthy();
    expect(screen.queryByText(mockEn.auth.deleteAccount)).toBeNull();
  });

  it('opens PersonalInfo from the complete profile card', () => {
    const screen = render(<AccountScreen />);

    fireEvent.press(screen.getByTestId('personal-settings-open'));

    expect(mockNavigate).toHaveBeenCalledWith('PersonalInfo');
  });

  it('opens an internationalized logout confirmation dialog', () => {
    const screen = render(<AccountScreen />);

    fireEvent.press(screen.getByTestId('logout-button'));

    const dialog = screen.getByTestId('confirmation-dialog');
    expect(dialog.props.role).toBe('alertdialog');
    expect(within(dialog).getAllByText(mockEn.auth.logout)).toHaveLength(2);
    expect(within(dialog).getByText(mockEn.auth.logoutConfirm)).toBeTruthy();
    expect(within(dialog).getByText(mockEn.common.cancel)).toBeTruthy();
  });

  it('closes the logout dialog without dispatching when cancelled', () => {
    const screen = render(<AccountScreen />);

    fireEvent.press(screen.getByTestId('logout-button'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-cancel'));

    expect(screen.queryByTestId('confirmation-dialog')).toBeNull();
    expect(logout).not.toHaveBeenCalled();
    expect(mockDispatch).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('dispatches logout once and replaces the route only after it completes', async () => {
    let resolveLogout: (() => void) | undefined;
    const pendingLogout = new Promise<void>((resolve) => {
      resolveLogout = resolve;
    });
    mockDispatch.mockReturnValueOnce(pendingLogout);
    const screen = render(<AccountScreen />);

    fireEvent.press(screen.getByTestId('logout-button'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));

    expect(logout).toHaveBeenCalledTimes(1);
    expect(mockDispatch).toHaveBeenCalledTimes(1);
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'auth/logout' });
    expect(mockReplace).not.toHaveBeenCalled();

    await act(async () => {
      resolveLogout?.();
      await pendingLogout;
    });

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledTimes(1);
      expect(mockReplace).toHaveBeenCalledWith('Welcome');
      expect(screen.queryByTestId('confirmation-dialog')).toBeNull();
    });
  });
});
