/**
 * iOS 风格列表项组件
 * 图标 + 文本 + 箭头，支持进入动画
 */

import React, { useEffect, useRef } from 'react';
import {
  TouchableOpacity,
  View,
  Text,
  StyleSheet,
  Animated,
  StyleProp,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';
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
}

const ListItem: React.FC<ListItemProps> = ({
  icon,
  label,
  onPress,
  showArrow = true,
  style,
  labelStyle,
  index = 0,
  disabled = false,
}) => {
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const translateX = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 300,
        delay: index * 30,
        useNativeDriver: true,
      }),
      Animated.timing(translateX, {
        toValue: 0,
        duration: 300,
        delay: index * 30,
        useNativeDriver: true,
      }),
    ]).start();
  }, [fadeAnim, translateX, index]);

  return (
    <Animated.View
      style={[
        {
          opacity: fadeAnim,
          transform: [{ translateX }],
        },
      ]}
    >
      <TouchableOpacity
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
              color={icon.color || COLORS.TEXT_PRIMARY}
              style={[styles.icon, icon.style]}
            />
          )}
          <Text style={[styles.label, labelStyle]}>{label}</Text>
        </View>
        {showArrow && (
          <Icon
            name="chevron-forward"
            library="Ionicons"
            size={20}
            color={COLORS.IOS_GRAY}
          />
        )}
      </TouchableOpacity>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: IOS_STYLES.SPACING.MD,
    paddingVertical: IOS_STYLES.SPACING.MD,
    backgroundColor: COLORS.CARD_BG,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.IOS_SEPARATOR,
  },
  leftContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  icon: {
    marginRight: IOS_STYLES.SPACING.MD,
  },
  label: {
    fontSize: IOS_STYLES.FONT_SIZE.MEDIUM,
    color: COLORS.TEXT_PRIMARY,
    fontWeight: IOS_STYLES.FONT_WEIGHT.REGULAR,
  },
  disabled: {
    opacity: 0.5,
  },
});

export default ListItem;
