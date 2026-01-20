/**
 * iOS 风格按钮组件
 * 支持主要、次要、文本按钮，带有按压动画效果
 */

import React, { useRef } from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  StyleProp,
  ViewStyle,
  TextStyle,
  Animated,
  ActivityIndicator,
  View,
} from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';
import Icon, { IconProps } from './Icon';

export type ButtonVariant = 'primary' | 'secondary' | 'text' | 'outline';
export type ButtonSize = 'small' | 'medium' | 'large';

export interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  icon?: IconProps;
  iconPosition?: 'left' | 'right';
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}

const Button: React.FC<ButtonProps> = ({
  title,
  onPress,
  variant = 'primary',
  size = 'medium',
  disabled = false,
  loading = false,
  icon,
  iconPosition = 'left',
  style,
  textStyle,
}) => {
  const scaleValue = useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    Animated.spring(scaleValue, {
      toValue: 0.96,
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

  const getVariantStyles = (): { container: ViewStyle; text: TextStyle } => {
    const baseContainer: ViewStyle = {
      borderRadius: IOS_STYLES.RADIUS.MEDIUM,
      justifyContent: 'center',
      alignItems: 'center',
      flexDirection: 'row',
    };

    const baseText: TextStyle = {
      fontWeight: IOS_STYLES.FONT_WEIGHT.SEMIBOLD,
    };

    switch (variant) {
      case 'primary':
        return {
          container: {
            ...baseContainer,
            backgroundColor: COLORS.IOS_BLUE,
            ...IOS_STYLES.SHADOW.SMALL,
          },
          text: {
            ...baseText,
            color: COLORS.IOS_WHITE,
          },
        };
      case 'secondary':
        return {
          container: {
            ...baseContainer,
            backgroundColor: COLORS.IOS_LIGHT_GRAY,
          },
          text: {
            ...baseText,
            color: COLORS.TEXT_PRIMARY,
          },
        };
      case 'outline':
        return {
          container: {
            ...baseContainer,
            backgroundColor: 'transparent',
            borderWidth: 1,
            borderColor: COLORS.IOS_SEPARATOR,
          },
          text: {
            ...baseText,
            color: COLORS.IOS_BLUE,
          },
        };
      case 'text':
        return {
          container: {
            ...baseContainer,
            backgroundColor: 'transparent',
          },
          text: {
            ...baseText,
            color: COLORS.IOS_BLUE,
          },
        };
      default:
        // 默认返回 primary 样式
        return {
          container: {
            ...baseContainer,
            backgroundColor: COLORS.IOS_BLUE,
            ...IOS_STYLES.SHADOW.SMALL,
          },
          text: {
            ...baseText,
            color: COLORS.IOS_WHITE,
          },
        };
    }
  };

  const getSizeStyles = (): { container: ViewStyle; text: TextStyle } => {
    switch (size) {
      case 'small':
        return {
          container: {
            paddingVertical: 8,
            paddingHorizontal: 16,
          },
          text: {
            fontSize: IOS_STYLES.FONT_SIZE.BODY,
          },
        };
      case 'large':
        return {
          container: {
            paddingVertical: 16,
            paddingHorizontal: 24,
          },
          text: {
            fontSize: IOS_STYLES.FONT_SIZE.MEDIUM,
          },
        };
      case 'medium':
      default:
        return {
          container: {
            paddingVertical: 12,
            paddingHorizontal: 20,
          },
          text: {
            fontSize: IOS_STYLES.FONT_SIZE.BODY,
          },
        };
    }
  };

  const variantStyles = getVariantStyles();
  const sizeStyles = getSizeStyles();

  const isDisabled = disabled || loading;
  const opacity = isDisabled ? 0.5 : 1;

  const renderIcon = () => {
    if (!icon || loading) return null;
    return (
      <Icon
        {...icon}
        style={[
          iconPosition === 'left' ? { marginRight: 8 } : { marginLeft: 8 },
          icon.style,
        ]}
      />
    );
  };

  const renderContent = () => {
    if (loading) {
      return (
        <View style={styles.loadingContainer}>
          <ActivityIndicator
            size="small"
            color={variant === 'primary' ? COLORS.IOS_WHITE : COLORS.IOS_BLUE}
          />
          <Text
            style={[
              variantStyles.text,
              sizeStyles.text,
              { marginLeft: 8 },
              textStyle,
            ]}
          >
            {title}
          </Text>
        </View>
      );
    }

    if (iconPosition === 'left') {
      return (
        <>
          {renderIcon()}
          <Text style={[variantStyles.text, sizeStyles.text, textStyle]}>
            {title}
          </Text>
        </>
      );
    }

    return (
      <>
        <Text style={[variantStyles.text, sizeStyles.text, textStyle]}>
          {title}
        </Text>
        {renderIcon()}
      </>
    );
  };

  return (
    <TouchableOpacity
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={isDisabled}
      activeOpacity={0.8}
      style={[
        variantStyles.container,
        sizeStyles.container,
        { opacity },
        style,
      ]}
    >
      <Animated.View style={{ transform: [{ scale: scaleValue }] }}>
        {renderContent()}
      </Animated.View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  loadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default Button;
