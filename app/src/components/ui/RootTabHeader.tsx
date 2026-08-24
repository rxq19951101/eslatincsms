import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import BrandLogo from '../brand/BrandLogo';
import { COLORS } from '../../constants/config';

interface RootTabHeaderProps {
  title: string;
  subtitle?: string;
  showBrandMark?: boolean;
  rightAction?: React.ReactNode;
  testID?: string;
}

const RootTabHeader: React.FC<RootTabHeaderProps> = ({
  title,
  subtitle,
  showBrandMark = false,
  rightAction,
  testID = 'app-root-tab-header',
}) => (
  <View testID={testID} style={styles.container}>
    <View style={styles.row}>
      {showBrandMark && (
        <View testID={`${testID}-brand`} style={styles.brandMark}>
          <BrandLogo compact style={styles.brandArtwork} accessibilityLabel="EsLatin" />
        </View>
      )}
      <View style={styles.copy}>
        <Text style={styles.title}>{title}</Text>
        {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      </View>
      {!!rightAction && <View style={styles.action}>{rightAction}</View>}
    </View>
  </View>
);

const styles = StyleSheet.create({
  container: {
    width: '100%',
    maxWidth: 960,
    alignSelf: 'center',
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 16,
  },
  row: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
  },
  brandMark: {
    width: 44,
    height: 36,
    marginRight: 12,
    overflow: 'hidden',
  },
  brandArtwork: {
    width: 44,
    height: 43,
    marginTop: -1,
  },
  copy: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '800',
    letterSpacing: -0.4,
    color: COLORS.TEXT_PRIMARY,
  },
  subtitle: {
    marginTop: 3,
    maxWidth: 520,
    fontSize: 14,
    lineHeight: 20,
    color: COLORS.TEXT_SECONDARY,
  },
  action: {
    marginLeft: 16,
  },
});

export default RootTabHeader;
