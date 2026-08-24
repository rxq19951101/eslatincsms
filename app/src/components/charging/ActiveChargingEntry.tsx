import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useAppSelector } from '../../hooks/useRedux';
import { useI18n } from '../../i18n';
import { navigationRef } from '../../navigation/navigationRef';
import { palette, spacing, typography } from '../../theme';
import { publicChargerIdentity } from '../../utils/localizedDisplay';
import Icon from '../ui/Icon';

const ActiveChargingEntry = () => {
  const { t } = useI18n();
  const activeSession = useAppSelector((state) => state.charging.activeSession);

  if (!activeSession) return null;

  const openSession = () => {
    if (navigationRef.isReady()) {
      navigationRef.navigate('ChargingProcess', { sessionId: activeSession.id });
    }
  };

  return (
    <TouchableOpacity
      testID="active-charging-entry"
      accessibilityRole="button"
      accessibilityLabel={t.charging.activeSessionEntry}
      onPress={openSession}
      style={styles.entry}
    >
      <View style={styles.text}>
        <Text style={styles.title}>{t.charging.activeSessionEntry}</Text>
        <Text style={styles.subtitle} numberOfLines={1}>
          {publicChargerIdentity(activeSession, t.common.unknown)}
        </Text>
      </View>
      <Icon name="chevron-forward" size={20} color={palette.surface} />
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  entry: {
    minHeight: 52,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: palette.brandStrong,
    flexDirection: 'row',
    alignItems: 'center',
  },
  text: {
    flex: 1,
  },
  title: {
    color: palette.surface,
    fontSize: typography.body,
    fontWeight: typography.semibold,
  },
  subtitle: {
    color: palette.surface,
    fontSize: typography.caption,
    opacity: 0.85,
  },
});

export default ActiveChargingEntry;
