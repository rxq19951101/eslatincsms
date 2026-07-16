/**
 * 低噪音内容容器。默认不加阴影，只有 elevated 场景才建立层级。
 */

import React, { useRef } from 'react';
import {
  TouchableOpacity,
  StyleProp,
  ViewStyle,
  Animated,
} from 'react-native';
import { palette, radius, shadow } from '../../theme';

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
      backgroundColor: palette.surface,
      borderRadius: radius.lg,
    };

    switch (variant) {
      case 'elevated':
        return {
          ...baseStyle,
          ...shadow.raised,
        };
      case 'outlined':
        return {
          ...baseStyle,
          borderWidth: 1,
          borderColor: palette.border,
        };
      case 'default':
      default:
        return {
          ...baseStyle,
          borderWidth: 1,
          borderColor: palette.border,
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
