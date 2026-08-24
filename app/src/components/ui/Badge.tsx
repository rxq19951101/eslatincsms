/**
 * 统一状态徽标组件
 * 用于充电桩/连接器/账单等状态展示，替代各页面各自实现的状态色块，
 * 保证颜色语义（成功/警告/错误/中性）与圆角、字号在全 App 内一致
 */

import React from 'react';
import { View, Text, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const VARIANT_COLORS: Record<BadgeVariant, string> = {
  success: COLORS.SUCCESS,
  warning: COLORS.WARNING,
  error: COLORS.ERROR,
  info: COLORS.SECONDARY,
  neutral: COLORS.IOS_GRAY,
};

export interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  /** 自定义覆盖色，优先级高于 variant */
  color?: string;
  /** 点状徽标（用于列表内的轻量状态提示），默认为实心色块 */
  dot?: boolean;
  style?: StyleProp<ViewStyle>;
}

const Badge: React.FC<BadgeProps> = ({ label, variant = 'neutral', color, dot = false, style }) => {
  const tint = color || VARIANT_COLORS[variant];

  if (dot) {
    return (
      <View style={[styles.dotContainer, style]}>
        <View style={[styles.dot, { backgroundColor: tint }]} />
        <Text style={[styles.dotLabel, { color: tint }]} numberOfLines={1}>
          {label}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.pill, { backgroundColor: tint }, style]}>
      <Text style={styles.pillLabel} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: IOS_STYLES.SPACING.SM + 2,
    paddingVertical: 5,
    borderRadius: IOS_STYLES.RADIUS.ROUND,
    alignSelf: 'flex-start',
  },
  pillLabel: {
    color: COLORS.IOS_WHITE,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
  },
  dotContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginRight: 6,
  },
  dotLabel: {
    fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    fontSize: IOS_STYLES.FONT_SIZE.SMALL,
  },
});

export default Badge;
