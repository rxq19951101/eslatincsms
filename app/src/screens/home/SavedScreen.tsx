import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, StatusBar, Text, View } from 'react-native';
import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { getFavoriteSites } from '../../api/favorites';
import type { SiteSummary } from '../../api/sites';
import Card from '../../components/ui/Card';
import Badge, { type BadgeVariant } from '../../components/ui/Badge';
import Screen from '../../components/ui/Screen';
import RootTabHeader from '../../components/ui/RootTabHeader';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import type { RootStackParamList } from '../../types';
import { localizeStatus } from '../../utils/localizeStatus';

const SavedScreen = () => {
  const { t } = useI18n();
  const navigation = useNavigation<StackNavigationProp<RootStackParamList>>();
  const isFocused = useIsFocused();
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadFavorites = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setSites(await getFavoriteSites());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isFocused) loadFavorites();
  }, [isFocused, loadFavorites]);

  const renderSite = ({ item }: { item: SiteSummary }) => {
    const variant: BadgeVariant = item.status === 'Available'
      ? 'success'
      : item.status === 'Charging'
      ? 'warning'
      : item.status === 'Offline' || item.status === 'Faulted'
      ? 'error'
      : 'neutral';
    return (
      <Card
        testID={`app-saved-site-${item.id}`}
        accessibilityLabel={`${item.name}, ${item.address}`}
        onPress={() => navigation.navigate('StationDetail', { siteId: item.id })}
        style={styles.card}
      >
        <View style={styles.row}>
          <View style={styles.copy}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.address} numberOfLines={1}>{item.address}</Text>
            <Text style={styles.availability}>
              {item.available_connectors}/{item.total_connectors} {t.station.connectors}
            </Text>
          </View>
          <Badge label={localizeStatus(item.status, t)} variant={variant} />
        </View>
      </Card>
    );
  };

  return (
    <Screen>
      <StatusBar barStyle="dark-content" />
      <RootTabHeader title={t.saved.title} testID="app-saved-header" />
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.PRIMARY} /></View>
      ) : error ? (
        <View style={styles.center}><Text style={styles.emptyTitle}>{t.saved.loadFailed}</Text></View>
      ) : (
        <FlatList
          data={sites}
          keyExtractor={(item) => item.id}
          renderItem={renderSite}
          contentContainerStyle={sites.length ? styles.list : styles.emptyList}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>{t.saved.emptyTitle}</Text>
              <Text style={styles.emptySubtitle}>{t.saved.emptySubtitle}</Text>
            </View>
          }
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  list: { paddingHorizontal: 20, paddingBottom: 24 },
  card: { padding: 16, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  copy: { flex: 1, paddingRight: 12 },
  name: { fontSize: 17, fontWeight: '700', color: COLORS.TEXT_PRIMARY },
  address: { marginTop: 5, color: COLORS.TEXT_SECONDARY },
  availability: { marginTop: 10, color: COLORS.PRIMARY, fontWeight: '600' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  emptyList: { flexGrow: 1 },
  emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 40 },
  emptyTitle: { fontSize: 18, fontWeight: '600', color: COLORS.TEXT_PRIMARY, marginBottom: 8 },
  emptySubtitle: { fontSize: 14, color: COLORS.TEXT_SECONDARY, textAlign: 'center' },
});

export default SavedScreen;
