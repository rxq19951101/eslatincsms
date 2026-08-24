/**
 * 统一图标组件
 * App-wide Ionicons wrapper. A single icon family keeps weight and geometry consistent.
 */

import React, { useEffect } from 'react';
import { Animated, StyleProp, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export type IconLibrary = 'Ionicons';
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

  const renderIcon = () => (
    <Ionicons name={name as any} size={size} color={color} style={style} />
  );

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
