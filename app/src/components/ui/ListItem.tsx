/**
 * 内容优先的列表项。图标是可选语义，不用于装饰。
 */

import React from 'react';
import {
  TouchableOpacity,
  View,
  Text,
  StyleSheet,
  StyleProp,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { palette, spacing, typography } from '../../theme';
import Icon, { IconProps } from './Icon';

export interface ListItemProps {
  icon?: IconProps;
  label: string;
  onPress: () => void;
  showArrow?: boolean;
  style?: StyleProp<ViewStyle>;
  labelStyle?: StyleProp<TextStyle>;
  index?: number;
  disabled?: boolean;
  testID?: string;
  accessibilityLabel?: string;
  accessibilityHint?: string;
}

const ListItem: React.FC<ListItemProps> = ({
  icon,
  label,
  onPress,
  showArrow = true,
  style,
  labelStyle,
  index: _index = 0,
  disabled = false,
  testID,
  accessibilityLabel = label,
  accessibilityHint,
}) => {
  return (
    <View>
      <TouchableOpacity
        testID={testID}
        accessibilityLabel={accessibilityLabel}
        accessibilityHint={accessibilityHint}
        accessibilityRole="button"
        style={[
          styles.container,
          disabled && styles.disabled,
          style,
        ]}
        onPress={onPress}
        disabled={disabled}
        activeOpacity={0.7}
      >
        <View style={styles.leftContent}>
          {icon && (
            <Icon
              {...icon}
              size={icon.size || 20}
              color={icon.color || palette.ink}
              style={[styles.icon, icon.style]}
            />
          )}
          <Text style={[styles.label, labelStyle]}>{label}</Text>
        </View>
        {showArrow && (
          <Icon
            name="chevron-forward"
            library="Ionicons"
            size={18}
            color={palette.subtle}
          />
        )}
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    minHeight: 52,
    paddingVertical: 14,
    backgroundColor: palette.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: palette.border,
  },
  leftContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  icon: {
    marginRight: spacing.sm + 4,
  },
  label: {
    fontSize: typography.label,
    color: palette.ink,
    fontWeight: typography.medium,
  },
  disabled: {
    opacity: 0.5,
  },
});

export default ListItem;
