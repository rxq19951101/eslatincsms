/**
 * 骨架屏组件
 * 用于加载状态的占位符
 */

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, StyleProp, ViewStyle } from 'react-native';
import { COLORS, IOS_STYLES } from '../../constants/config';

export interface SkeletonProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: StyleProp<ViewStyle>;
}

const Skeleton: React.FC<SkeletonProps> = ({
  width = '100%',
  height = 20,
  borderRadius = IOS_STYLES.RADIUS.SMALL,
  style,
}) => {
  const shimmerAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const shimmer = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmerAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(shimmerAnim, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    );
    shimmer.start();
    return () => shimmer.stop();
  }, [shimmerAnim]);

  const opacity = shimmerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius,
          backgroundColor: COLORS.BORDER,
          opacity,
        },
        style,
      ]}
    />
  );
};

export interface SkeletonCardProps {
  count?: number;
}

export const SkeletonCard: React.FC<SkeletonCardProps> = ({ count = 1 }) => {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <View
          key={index}
          style={[
            styles.cardContainer,
            { marginBottom: index < count - 1 ? IOS_STYLES.SPACING.MD : 0 },
          ]}
        >
          <Skeleton width="60%" height={20} style={{ marginBottom: 8 }} />
          <Skeleton width="80%" height={16} style={{ marginBottom: 12 }} />
          <View style={styles.row}>
            <Skeleton width={60} height={16} />
            <Skeleton width={80} height={16} style={{ marginLeft: 16 }} />
          </View>
        </View>
      ))}
    </>
  );
};

const styles = StyleSheet.create({
  cardContainer: {
    backgroundColor: COLORS.CARD_BG,
    borderRadius: IOS_STYLES.RADIUS.MEDIUM,
    padding: IOS_STYLES.SPACING.MD,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    ...IOS_STYLES.SHADOW.SMALL,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
});

export default Skeleton;
