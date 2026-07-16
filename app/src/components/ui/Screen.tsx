import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { SafeAreaView, Edge } from 'react-native-safe-area-context';
import { palette } from '../../theme';

interface ScreenProps {
  children: React.ReactNode;
  edges?: Edge[];
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
}

const Screen: React.FC<ScreenProps> = ({ children, edges = ['top'], style, contentStyle }) => (
  <SafeAreaView style={[styles.safeArea, style]} edges={edges}>
    <View style={[styles.content, contentStyle]}>{children}</View>
  </SafeAreaView>
);

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: palette.canvas },
  content: { flex: 1 },
});

export default Screen;

