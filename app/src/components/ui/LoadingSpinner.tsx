/**
 * iOS 风格加载动画组件
 */

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, ActivityIndicator, Text, StyleProp, ViewStyle, TextStyle, Animated } from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';

export interface LoadingSpinnerProps {
  size?: 'small' | 'large';
  color?: string;
  text?: string;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'large',
  color = COLORS.IOS_BLUE,
  text,
  style,
  textStyle,
}) => {
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  return (
    <Animated.View style={[styles.container, { opacity: fadeAnim }, style]}>
      <ActivityIndicator size={size} color={color} />
      {text && (
        <Text style={[styles.text, textStyle]}>
          {text}
        </Text>
      )}
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: IOS_STYLES.SPACING.XL,
  },
  text: {
    marginTop: IOS_STYLES.SPACING.MD,
    fontSize: IOS_STYLES.FONT_SIZE.BODY,
    color: COLORS.TEXT_SECONDARY,
  },
});

export default LoadingSpinner;
