import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { LocalizedDateInput } from '@/components/ui/localized-date-input';
import { I18nProvider, type Locale } from '@/lib/i18n';

function renderDateInput(locale: Locale, value = '') {
  window.localStorage.setItem('admin_locale', locale);
  const onChange = vi.fn();
  render(
    <I18nProvider>
      <LocalizedDateInput
        value={value}
        onChange={onChange}
        aria-label="Start date"
        testId="date-input"
      />
    </I18nProvider>,
  );
  return onChange;
}

describe('LocalizedDateInput', () => {
  it.each([
    ['zh-CN', '选择日期'],
    ['en', 'Select date'],
    ['es', 'Seleccionar fecha'],
  ] as const)('renders the %s placeholder', async (locale, placeholder) => {
    renderDateInput(locale);
    await waitFor(() => expect(screen.getByTestId('date-input')).toHaveTextContent(placeholder));
  });

  it('renders Spanish calendar controls and returns an API-safe date', async () => {
    const user = userEvent.setup();
    const onChange = renderDateInput('es', '2026-07-21');

    await waitFor(() => expect(screen.getByTestId('date-input')).toHaveTextContent('21/07/2026'));
    await user.click(screen.getByTestId('date-input'));

    expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mes siguiente' })).toBeInTheDocument();
    expect(screen.getByText('julio 2026')).toBeInTheDocument();
    expect(screen.getByText('Borrar')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /22 de julio de 2026/i }));
    expect(onChange).toHaveBeenCalledWith('2026-07-22');
  });
});
