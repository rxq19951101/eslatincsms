/**
 * 弧形进度圈组件
 * 用于显示充电进度、电量等信息
 * 使用 React Native 内置的 Animated API，避免依赖 react-native-reanimated
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { View, Text, StyleSheet, StyleProp, ViewStyle, Animated, Easing } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { COLORS } from '../../constants/config';

export interface CircularProgressProps {
  /** 进度百分比 (0-100) */
  progress: number;
  /** 组件大小 */
  size?: number;
  /** 圆环宽度 */
  strokeWidth?: number;
  /** 进度颜色 */
  progressColor?: string;
  /** 背景颜色 */
  backgroundColor?: string;
  /** 中心主文本 */
  mainText?: string;
  /** 中心副文本 */
  subText?: string;
  /** 底部信息 */
  bottomInfo?: {
    label: string;
    value: string;
  }[];
  /** 自定义样式 */
  style?: StyleProp<ViewStyle>;
}

const CircularProgress: React.FC<CircularProgressProps> = ({
  progress,
  size = 200,
  strokeWidth = 12,
  progressColor = COLORS.PRIMARY,
  backgroundColor = COLORS.BORDER,
  mainText,
  subText,
  bottomInfo = [],
  style,
}) => {
  const animatedProgress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(animatedProgress, {
      toValue: Math.min(Math.max(progress, 0), 100),
      duration: 800,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false, // SVG 属性不支持 native driver
    }).start();
  }, [progress, animatedProgress]);

  const radius = (size - strokeWidth) / 2;
  const center = size / 2;

  // 创建进度弧路径
  const createArcPath = useCallback((progressPercent: number) => {
    const startAngle = -90; // 从顶部开始
    const endAngle = startAngle + (360 * progressPercent / 100);
    
    const startAngleRad = (startAngle * Math.PI) / 180;
    const endAngleRad = (endAngle * Math.PI) / 180;
    
    const startX = center + radius * Math.cos(startAngleRad);
    const startY = center + radius * Math.sin(startAngleRad);
    const endX = center + radius * Math.cos(endAngleRad);
    const endY = center + radius * Math.sin(endAngleRad);
    
    const largeArcFlag = progressPercent > 50 ? 1 : 0;
    
    return `M ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY}`;
  }, [radius, center]);

  // 使用状态来跟踪当前的进度路径
  const [path, setPath] = useState(() => createArcPath(0));

  useEffect(() => {
    const listenerId = animatedProgress.addListener(({ value }) => {
      setPath(createArcPath(value));
    });

    return () => {
      animatedProgress.removeListener(listenerId);
    };
  }, [animatedProgress, createArcPath]);

  return (
    <View style={[styles.container, { width: size, height: size }, style]}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 背景圆环 */}
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke={backgroundColor}
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* 进度弧线 */}
        <Path
          d={path}
          stroke={progressColor}
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
        />
      </Svg>

      {/* 中心内容 */}
      <View style={styles.content}>
        {mainText && <Text style={[styles.mainText, { fontSize: size * 0.2 }]}>{mainText}</Text>}
        {subText && <Text style={[styles.subText, { fontSize: size * 0.1 }]}>{subText}</Text>}
      </View>

      {/* 底部信息 */}
      {bottomInfo.length > 0 && (
        <View style={styles.bottomInfo}>
          {bottomInfo.map((info, index) => (
            <View key={index} style={styles.bottomInfoItem}>
              <Text style={styles.bottomInfoLabel}>{info.label}</Text>
              <Text style={styles.bottomInfoValue}>{info.value}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  content: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
  },
  mainText: {
    fontWeight: '900',
    color: COLORS.TEXT_PRIMARY,
    textAlign: 'center',
  },
  subText: {
    fontWeight: '600',
    color: COLORS.TEXT_SECONDARY,
    marginTop: 4,
    textAlign: 'center',
  },
  bottomInfo: {
    position: 'absolute',
    bottom: -40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
  },
  bottomInfoItem: {
    alignItems: 'center',
  },
  bottomInfoLabel: {
    fontSize: 12,
    color: COLORS.TEXT_SECONDARY,
    marginBottom: 4,
  },
  bottomInfoValue: {
    fontSize: 16,
    fontWeight: '800',
    color: COLORS.TEXT_PRIMARY,
  },
});

export default CircularProgress;
