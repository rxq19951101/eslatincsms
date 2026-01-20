/**
 * 统一图标组件
 * 封装 Expo Vector Icons，支持多种图标库和动画效果
 */

import React, { useEffect } from 'react';
import { Animated, StyleProp, TextStyle } from 'react-native';
import { Ionicons, MaterialIcons, FontAwesome, FontAwesome5 } from '@expo/vector-icons';

export type IconLibrary = 'Ionicons' | 'MaterialIcons' | 'FontAwesome' | 'FontAwesome5';
export type IconAnimation = 'none' | 'spin' | 'pulse';

export interface IconProps {
  name: string;
  library?: IconLibrary;
  size?: number;
  color?: string;
  style?: StyleProp<TextStyle>;
  animation?: IconAnimation;
  animating?: boolean;
}

const Icon: React.FC<IconProps> = ({
  name,
  library = 'Ionicons',
  size = 24,
  color = '#000000',
  style,
  animation = 'none',
  animating = false,
}) => {
  const spinValue = React.useRef(new Animated.Value(0)).current;
  const pulseValue = React.useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (animation === 'spin' && animating) {
      const spin = Animated.loop(
        Animated.timing(spinValue, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        })
      );
      spin.start();
      return () => spin.stop();
    } else if (animation === 'pulse' && animating) {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseValue, {
            toValue: 1.2,
            duration: 500,
            useNativeDriver: true,
          }),
          Animated.timing(pulseValue, {
            toValue: 1,
            duration: 500,
            useNativeDriver: true,
          }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    }
  }, [animation, animating, spinValue, pulseValue]);

  const spin = spinValue.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const renderIcon = () => {
    const commonProps = {
      name: name as any,
      size,
      color,
      style,
    };

    switch (library) {
      case 'MaterialIcons':
        return <MaterialIcons {...commonProps} />;
      case 'FontAwesome':
        return <FontAwesome {...commonProps} />;
      case 'FontAwesome5':
        return <FontAwesome5 {...commonProps} />;
      case 'Ionicons':
      default:
        return <Ionicons {...commonProps} />;
    }
  };

  if (animation === 'spin' && animating) {
    return (
      <Animated.View
        style={{
          transform: [{ rotate: spin }],
        }}
      >
        {renderIcon()}
      </Animated.View>
    );
  }

  if (animation === 'pulse' && animating) {
    return (
      <Animated.View
        style={{
          transform: [{ scale: pulseValue }],
        }}
      >
        {renderIcon()}
      </Animated.View>
    );
  }

  return renderIcon();
};

export default Icon;
