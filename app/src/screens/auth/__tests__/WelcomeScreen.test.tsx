import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import WelcomeScreen from '../WelcomeScreen';

const mockNavigate = jest.fn();
let mockTranslations = {
  appName: 'EsLatin',
  tagline: 'Encuentra y carga tu vehículo eléctrico',
  auth: {
    signInEmail: 'Iniciar sesión con correo',
    noAccount: '¿No tienes cuenta?',
    signUp: 'Registrarse',
  },
};

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../../i18n', () => ({
  useI18n: () => ({ t: mockTranslations }),
}));

const translations = {
  es: {
    appName: 'EsLatin',
    tagline: 'Encuentra y carga tu vehículo eléctrico',
    auth: {
      signInEmail: 'Iniciar sesión con correo',
      noAccount: '¿No tienes cuenta?',
      signUp: 'Registrarse',
    },
  },
  en: {
    appName: 'EsLatin',
    tagline: 'Find and charge your electric vehicle',
    auth: {
      signInEmail: 'Sign in with email',
      noAccount: "Don't have an account?",
      signUp: 'Sign up',
    },
  },
  zh: {
    appName: 'EsLatin',
    tagline: '查找并为你的电动车充电',
    auth: {
      signInEmail: '使用邮箱登录',
      noAccount: '还没有账号？',
      signUp: '注册',
    },
  },
} as const;

describe('WelcomeScreen', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockTranslations = translations.es;
  });

  it('uses the official white-background logo without repeating the brand name', () => {
    const screen = render(<WelcomeScreen />);

    expect(screen.getByTestId('welcome-brand-logo')).toHaveProp(
      'accessibilityLabel',
      'EsLatin'
    );
    expect(screen.queryByText('EsLatin')).toBeNull();
  });

  it('keeps the email login and registration navigation entries accessible', () => {
    const screen = render(<WelcomeScreen />);

    fireEvent.press(screen.getByTestId('welcome-email-sign-in'));
    expect(mockNavigate).toHaveBeenCalledWith('EmailLogin');

    fireEvent.press(screen.getByTestId('welcome-email-register'));
    expect(mockNavigate).toHaveBeenCalledWith('EmailRegister');
    expect(screen.getByTestId('welcome-email-register')).toHaveProp(
      'accessibilityLabel',
      translations.es.auth.signUp
    );
  });

  it.each(Object.entries(translations))(
    'renders %s copy from the active language',
    (_locale, copy) => {
      mockTranslations = copy;
      const screen = render(<WelcomeScreen />);

      expect(screen.getByText(copy.tagline)).toBeTruthy();
      expect(screen.getByText(copy.auth.signInEmail)).toBeTruthy();
      expect(screen.getByText(copy.auth.noAccount)).toBeTruthy();
      expect(screen.getByText(copy.auth.signUp)).toBeTruthy();
    }
  );
});
