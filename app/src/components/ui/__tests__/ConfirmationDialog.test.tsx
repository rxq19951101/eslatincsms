import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import ConfirmationDialog from '../ConfirmationDialog';

describe('ConfirmationDialog', () => {
  const defaultProps = {
    visible: true,
    title: 'Delete account',
    message: 'This cannot be undone.',
    cancelLabel: 'Cancel',
    confirmLabel: 'Delete',
    onCancel: jest.fn(),
    onConfirm: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders an accessible modal with cancel and confirm actions', () => {
    const screen = render(<ConfirmationDialog {...defaultProps} />);
    const dialog = screen.getByTestId('confirmation-dialog');

    expect(dialog.props.role).toBe('alertdialog');
    expect(dialog.props.accessibilityViewIsModal).toBe(true);
    expect(dialog.props['aria-modal']).toBe(true);
    expect(screen.getByText(defaultProps.title)).toBeTruthy();
    expect(screen.getByText(defaultProps.message)).toBeTruthy();
    expect(screen.getByRole('button', { name: defaultProps.cancelLabel })).toBeTruthy();
    expect(screen.getByRole('button', { name: defaultProps.confirmLabel })).toBeTruthy();
  });

  it('cancels without confirming and supports modal dismissal', () => {
    const screen = render(<ConfirmationDialog {...defaultProps} />);

    fireEvent.press(screen.getByTestId('confirmation-dialog-cancel'));
    screen.getByTestId('confirmation-dialog-modal').props.onRequestClose();

    expect(defaultProps.onCancel).toHaveBeenCalledTimes(2);
    expect(defaultProps.onConfirm).not.toHaveBeenCalled();
  });

  it('submits once and disables both actions while confirmation is pending', async () => {
    let resolveConfirmation: (() => void) | undefined;
    const onConfirm = jest.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveConfirmation = resolve;
        })
    );
    const screen = render(<ConfirmationDialog {...defaultProps} onConfirm={onConfirm} />);

    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));
    fireEvent.press(screen.getByTestId('confirmation-dialog-confirm'));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('confirmation-dialog-cancel')).toBeDisabled();
    expect(screen.getByTestId('confirmation-dialog-confirm')).toBeDisabled();
    screen.getByTestId('confirmation-dialog-modal').props.onRequestClose();
    expect(defaultProps.onCancel).not.toHaveBeenCalled();

    resolveConfirmation?.();
    await waitFor(() => {
      expect(screen.getByTestId('confirmation-dialog-cancel')).not.toBeDisabled();
    });
  });
});
