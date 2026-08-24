import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor, within } from '@testing-library/react-native';

import { en as mockEn } from '../../../i18n/en';
import PersonalInfoScreen from '../PersonalInfoScreen';
import { deleteAccount } from '../../../store/slices/authSlice';

const mockGoBack = jest.fn();
const mockReplace = jest.fn();
const mockUnwrap = jest.fn();
const mockDispatch = jest.fn(() => ({ unwrap: mockUnwrap }));
let mockIsLoading = false;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    goBack: mockGoBack,
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
          phone: '+57 300 000 0000',
        },
        isLoading: mockIsLoading,
      },
    }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEn }),
}));

jest.mock('../../../store/slices/authSlice', () => {
  return {
    deleteAccount: jest.fn(() => ({ type: 'auth/deleteAccount' })),
    setUser: jest.fn((user) => ({ type: 'auth/setUser', payload: user })),
  };
});

jest.mock('../../../utils/tokenManager', () => ({
  saveUserInfo: jest.fn(),
}));

jest.mock('../../../components/ui/Icon', () => {
  const { View } = require('react-native');
  return () => <View />;
});

describe('PersonalInfoScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsLoading = false;
    mockUnwrap.mockResolvedValue(undefined);
  });

  it('renders account management in an independent scrollable danger area', () => {
    const screen = render(<PersonalInfoScreen />);

    expect(screen.getByTestId('personal-settings-scroll-view')).toBeTruthy();
    expect(screen.getByTestId('account-management-section')).toBeTruthy();
    expect(screen.getByText(mockEn.personal.accountManagement)).toBeTruthy();
    expect(screen.getByText(mockEn.personal.deleteAccountDescription)).toBeTruthy();
    expect(screen.getByTestId('delete-account-button')).not.toBeDisabled();
  });

  it('opens the confirmation dialog and cancellation does not dispatch', () => {
    const screen = render(<PersonalInfoScreen />);

    fireEvent.press(screen.getByTestId('delete-account-button'));

    const dialog = screen.getByTestId('confirmation-dialog');
    expect(dialog.props.role).toBe('alertdialog');
    expect(within(dialog).getByText(mockEn.auth.deleteAccountTitle)).toBeTruthy();
    expect(within(dialog).getByText(mockEn.auth.deleteAccountMessage)).toBeTruthy();
    expect(deleteAccount).not.toHaveBeenCalled();

    fireEvent.press(screen.getByTestId('confirmation-dialog-cancel'));

    expect(screen.queryByTestId('confirmation-dialog')).toBeNull();
    expect(deleteAccount).not.toHaveBeenCalled();
    expect(mockDispatch).not.toHaveBeenCalled();
  });

  it('deletes only once after confirmation and keeps the success flow', async () => {
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = render(<PersonalInfoScreen />);

    fireEvent.press(screen.getByTestId('delete-account-button'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));

    await waitFor(() => {
      expect(deleteAccount).toHaveBeenCalledTimes(1);
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'auth/deleteAccount' });
      expect(alert).toHaveBeenCalledWith(mockEn.auth.deleteAccountSuccess);
      expect(mockReplace).toHaveBeenCalledWith('Welcome');
    });

    alert.mockRestore();
  });

  it('shows an inline internationalized error and stays on the page after failure', async () => {
    mockUnwrap.mockRejectedValue(new Error('server detail'));
    const screen = render(<PersonalInfoScreen />);

    fireEvent.press(screen.getByTestId('delete-account-button'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));

    await waitFor(() => {
      expect(screen.getByTestId('delete-account-error')).toHaveTextContent(mockEn.auth.deleteAccountError);
      expect(screen.queryByTestId('confirmation-dialog')).toBeNull();
      expect(mockReplace).not.toHaveBeenCalled();
    });
  });

  it('preserves the Redux loading state on the delete action', () => {
    mockIsLoading = true;
    const screen = render(<PersonalInfoScreen />);

    expect(screen.getByTestId('delete-account-button')).toBeDisabled();
  });
});
