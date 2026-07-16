/**
 * 统一的二级页面头部：返回按钮 + 居中标题 + 可选右侧操作
 *
 * 之前各页面各自实现头部时，左右两侧宽度经常不一致（例如返回按钮 44px、
 * 右侧按钮 64px），导致标题在视觉上并未真正居中、产生"错位"感。
 * 这里用绝对定位让标题始终以整个头部宽度为基准居中，不受左右内容宽度影响。
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';
import Icon from './Icon';

export interface ScreenHeaderProps {
  title: string;
  onBack?: () => void;
  /** 自定义左侧内容，提供时会覆盖默认返回按钮 */
  left?: React.ReactNode;
  right?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

const ScreenHeader: React.FC<ScreenHeaderProps> = ({ title, onBack, left, right, style }) => {
  return (
    <View style={[styles.header, style]}>
      <View style={styles.side}>
        {left ??
          (onBack && (
            <TouchableOpacity style={styles.backButton} onPress={onBack} activeOpacity={0.7}>
              <Icon name="arrow-back" library="Ionicons" size={24} color={COLORS.TEXT_PRIMARY} />
            </TouchableOpacity>
          ))}
      </View>

      <View style={styles.titleWrap} pointerEvents="none">
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
      </View>

      <View style={[styles.side, styles.sideRight]}>{right}</View>
    </View>
  );
};

const styles = StyleSheet.create({
  header: {
    height: 56,
    backgroundColor: COLORS.IOS_WHITE,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: IOS_STYLES.SPACING.SM,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.IOS_SEPARATOR,
  },
  side: {
    minWidth: 44,
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    zIndex: 1,
  },
  sideRight: {
    justifyContent: 'flex-end',
  },
  backButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  titleWrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 60,
  },
  title: {
    fontSize: IOS_STYLES.FONT_SIZE.MEDIUM,
    fontWeight: IOS_STYLES.FONT_WEIGHT.BOLD,
    color: COLORS.TEXT_PRIMARY,
  },
});

export default ScreenHeader;
