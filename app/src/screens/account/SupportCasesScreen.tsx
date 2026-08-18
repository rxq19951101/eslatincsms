import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { COLORS } from '../../constants/config';
import { useI18n } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import { formatDateTime } from '../../utils/localizedDisplay';
import { getSupportCases, PayMp002Error } from '../../features/payMp002/adapter';
import type { SupportCaseProjection } from '../../features/payMp002/types';
import Button from '../../components/ui/Button';

type Nav = StackNavigationProp<RootStackParamList, 'SupportCases'>;

const SupportCasesScreen = () => {
  const { t, locale } = useI18n();
  const navigation = useNavigation<Nav>();
  const [items, setItems] = useState<SupportCaseProjection[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<PayMp002Error | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const page = await getSupportCases({ limit: 50 });
      setItems(page.items);
    } catch (cause) {
      setError(cause instanceof PayMp002Error ? cause : null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <Screen testID="app-support-cases-screen" accessibilityLabel={t.history.supportCases}>
      <ScreenHeader title={t.history.supportCases} onBack={() => navigation.goBack()} />
      {error && <Text style={styles.error}>{t.history.loadFailed}</Text>}
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.PRIMARY} /><Text style={styles.centerText}>{t.common.loading}</Text></View>
      ) : error && items.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.error}>{t.history.loadFailed}</Text>
          <Button title={t.common.retry} onPress={() => void load()} variant="outline" size="small" style={styles.retry} />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center}><Text style={styles.centerText}>{t.history.supportEmpty}</Text></View>
      ) : (
        <FlatList
          testID="app-support-cases-list"
          data={items}
          keyExtractor={(item) => item.case_id}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} />}
          renderItem={({ item }) => (
            <TouchableOpacity
              testID="app-support-case-row"
              style={styles.card}
              accessibilityRole="button"
              onPress={() => navigation.navigate('SupportCaseDetail', { caseId: item.case_id })}
            >
              <View style={styles.row}>
                <View style={styles.left}>
                  <Text style={styles.title}>{item.reference}</Text>
                  <Text style={styles.sub}>{item.category} · {item.status}</Text>
                  <Text style={styles.sub}>{formatDateTime(item.updated_at, locale)}</Text>
                </View>
                <Text style={styles.status}>{item.status}</Text>
              </View>
            </TouchableOpacity>
          )}
        />
      )}
    </Screen>
  );
};

const styles = StyleSheet.create({
  error: { color: COLORS.ERROR, fontWeight: '700', padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  centerText: { color: COLORS.TEXT_SECONDARY, marginTop: 8 },
  list: { padding: 16, paddingBottom: 24 },
  card: { backgroundColor: '#FFF', borderWidth: 1, borderColor: COLORS.BORDER, borderRadius: 14, padding: 14, marginBottom: 10 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  left: { flex: 1, paddingRight: 12 },
  title: { color: COLORS.TEXT_PRIMARY, fontWeight: '900' },
  sub: { color: COLORS.TEXT_SECONDARY, marginTop: 6, fontSize: 12 },
  status: { color: COLORS.PRIMARY, fontWeight: '800' },
  retry: { marginTop: 12 },
});

export default SupportCasesScreen;
