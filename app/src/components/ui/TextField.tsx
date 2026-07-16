import React from 'react';
import { StyleProp, StyleSheet, Text, TextInput, TextInputProps, TextStyle, View, ViewStyle } from 'react-native';
import { palette, radius, spacing, typography } from '../../theme';

interface TextFieldProps extends TextInputProps {
  label?: string;
  error?: string;
  inputStyle?: StyleProp<TextStyle>;
  containerStyle?: StyleProp<ViewStyle>;
}

const TextField: React.FC<TextFieldProps> = ({ label, error, inputStyle, containerStyle, ...props }) => (
  <View style={[styles.wrapper, containerStyle]}>
    {!!label && <Text style={styles.label}>{label}</Text>}
    <TextInput {...props} placeholderTextColor={palette.subtle}
      style={[styles.input, !!error && styles.inputError, inputStyle]} />
    {!!error && <Text style={styles.error}>{error}</Text>}
  </View>
);

const styles = StyleSheet.create({
  wrapper: { gap: spacing.sm },
  label: { color: palette.ink, fontSize: typography.body, fontWeight: typography.medium },
  input: { minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: palette.border,
    paddingHorizontal: spacing.md, backgroundColor: palette.surface, color: palette.ink, fontSize: typography.label },
  inputError: { borderColor: palette.danger },
  error: { color: palette.danger, fontSize: typography.caption },
});

export default TextField;
