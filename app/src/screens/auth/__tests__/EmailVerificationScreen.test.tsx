import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { Keyboard, Platform } from 'react-native';

import { es as mockEs } from '../../../i18n/es';
import EmailVerificationScreen from '../EmailVerificationScreen';
import { verifyEmailWithCode } from '../../../api/auth';

const mockReplace = jest.fn();
const mockDispatch = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ goBack: jest.fn(), navigate: jest.fn(), replace: mockReplace }),
  useRoute: () => ({ params: { email: 'driver@example.com' } }),
}));

jest.mock('react-redux', () => ({
  useDispatch: () => mockDispatch,
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockEs }),
}));

jest.mock('../../../api/auth', () => ({
  resendVerificationEmail: jest.fn(),
  verifyEmailWithCode: jest.fn(),
}));

jest.mock('../../../store/slices/authSlice', () => ({
  setUser: jest.fn((user) => ({ type: 'auth/setUser', payload: user })),
}));

describe('EmailVerificationScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('normalizes input to six digits and enables submit only when complete', async () => {
    (verifyEmailWithCode as jest.Mock).mockResolvedValue({ user: { id: 'user-1' } });
    const dismiss = jest.spyOn(Keyboard, 'dismiss').mockImplementation(() => undefined);
    const screen = render(<EmailVerificationScreen />);
    const input = screen.getByTestId('email-verification-code');
    const submit = screen.getByTestId('email-verification-submit');

    expect(input).toHaveProp('maxLength', 6);
    expect(input).toHaveProp('textContentType', 'oneTimeCode');
    expect(input).toHaveProp('returnKeyType', 'done');
    expect(submit).toBeDisabled();

    fireEvent.changeText(input, '12a34b5678');
    expect(input).toHaveProp('value', '123456');
    expect(submit).not.toBeDisabled();

    fireEvent(input, 'submitEditing');
    await waitFor(() => {
      expect(dismiss).toHaveBeenCalled();
      expect(verifyEmailWithCode).toHaveBeenCalledWith({
        email: 'driver@example.com',
        code: '123456',
      });
      expect(mockReplace).toHaveBeenCalledWith('VerificationSuccess');
    });
  });

  it('does not auto-focus or install a dismiss press area on Web', () => {
    jest.replaceProperty(Platform, 'OS', 'web');
    const dismiss = jest.spyOn(Keyboard, 'dismiss').mockImplementation(() => undefined);
    const screen = render(<EmailVerificationScreen />);
    const input = screen.getByTestId('email-verification-code');

    expect(input).toHaveProp('autoFocus', false);
    expect(screen.queryByTestId('email-verification-dismiss-area')).toBeNull();

    fireEvent.press(input);
    expect(dismiss).not.toHaveBeenCalled();
  });

  it.each(['ios', 'android'] as const)(
    'auto-focuses and dismisses the keyboard from the blank area on %s',
    (os) => {
      jest.replaceProperty(Platform, 'OS', os);
      const dismiss = jest.spyOn(Keyboard, 'dismiss').mockImplementation(() => undefined);
      const screen = render(<EmailVerificationScreen />);

      expect(screen.getByTestId('email-verification-code')).toHaveProp('autoFocus', true);

      fireEvent.press(screen.getByTestId('email-verification-dismiss-area'));
      expect(dismiss).toHaveBeenCalledTimes(1);
    },
  );
});
