import React, { useEffect, useRef, useState } from 'react';
import { Modal, StyleSheet, Text, View } from 'react-native';

import { palette, radius, shadow, spacing, typography } from '../../theme';
import Button from './Button';

export interface ConfirmationDialogProps {
  visible: boolean;
  title: string;
  message: string;
  cancelLabel: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
}

const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
  visible,
  title,
  message,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
  loading = false,
}) => {
  const confirmationInFlight = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isBusy = loading || isSubmitting;

  useEffect(() => {
    if (!visible) {
      confirmationInFlight.current = false;
      setIsSubmitting(false);
    }
  }, [visible]);

  const handleCancel = () => {
    if (!isBusy) {
      onCancel();
    }
  };

  const handleConfirm = async () => {
    if (isBusy || confirmationInFlight.current) return;

    confirmationInFlight.current = true;
    setIsSubmitting(true);
    try {
      await onConfirm();
    } finally {
      confirmationInFlight.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      testID="confirmation-dialog-modal"
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={handleCancel}
    >
      <View style={styles.backdrop}>
        <View
          testID="confirmation-dialog"
          role="alertdialog"
          aria-modal
          accessibilityViewIsModal
          accessibilityLabel={`${title}. ${message}`}
          onAccessibilityEscape={handleCancel}
          style={styles.dialog}
        >
          <Text accessibilityRole="header" style={styles.title}>
            {title}
          </Text>
          <Text style={styles.message}>{message}</Text>

          <View style={styles.actions}>
            <Button
              testID="confirmation-dialog-cancel"
              title={cancelLabel}
              onPress={handleCancel}
              variant="outline"
              disabled={isBusy}
              style={styles.action}
            />
            <Button
              testID="confirmation-dialog-confirm"
              title={confirmLabel}
              onPress={handleConfirm}
              variant="danger"
              disabled={isBusy}
              loading={isBusy}
              style={styles.action}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(16, 42, 67, 0.45)',
  },
  dialog: {
    width: '100%',
    maxWidth: 440,
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: palette.surface,
    ...shadow.raised,
  },
  title: {
    color: palette.ink,
    fontSize: typography.title,
    fontWeight: typography.bold,
  },
  message: {
    color: palette.muted,
    fontSize: typography.body,
    lineHeight: 21,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'flex-end',
  },
  action: {
    flex: 1,
  },
});

export default ConfirmationDialog;
