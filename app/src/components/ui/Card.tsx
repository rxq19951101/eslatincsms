/**
 * iOS 风格卡片组件
 * 支持毛玻璃效果背景，按压交互动画
 */

import React, { useRef } from 'react';
import {
  TouchableOpacity,
  StyleSheet,
  StyleProp,
  ViewStyle,
  Animated,
} from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';

export interface CardProps {
  children: React.ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
  variant?: 'default' | 'elevated' | 'outlined';
  interactive?: boolean;
}

const Card: React.FC<CardProps> = ({
  children,
  onPress,
  style,
  variant = 'default',
  interactive = false,
}) => {
  const scaleValue = useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    if (!interactive && !onPress) return;
    
    Animated.spring(scaleValue, {
      toValue: 0.98,
      useNativeDriver: true,
      friction: 3,
      tension: 40,
    }).start();
  };

  const handlePressOut = () => {
    Animated.spring(scaleValue, {
      toValue: 1,
      useNativeDriver: true,
      friction: 3,
      tension: 40,
    }).start();
  };

  const getVariantStyles = (): ViewStyle => {
    const baseStyle: ViewStyle = {
      backgroundColor: COLORS.CARD_BG,
      borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    };

    switch (variant) {
      case 'elevated':
        return {
          ...baseStyle,
          ...IOS_STYLES.SHADOW.MEDIUM,
        };
      case 'outlined':
        return {
          ...baseStyle,
          borderWidth: 1,
          borderColor: COLORS.BORDER,
        };
      case 'default':
      default:
        return {
          ...baseStyle,
          borderWidth: 1,
          borderColor: COLORS.BORDER,
          ...IOS_STYLES.SHADOW.SMALL,
        };
    }
  };

  const cardContent = (
    <Animated.View
      style={[
        getVariantStyles(),
        {
          transform: [{ scale: scaleValue }],
        },
        style,
      ]}
    >
      {children}
    </Animated.View>
  );

  if (onPress || interactive) {
    return (
      <TouchableOpacity
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        activeOpacity={1}
        disabled={!onPress}
      >
        {cardContent}
      </TouchableOpacity>
    );
  }

  return cardContent;
};

export default Card;
