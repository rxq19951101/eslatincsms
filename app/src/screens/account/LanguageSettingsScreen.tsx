import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import type { RootStackParamList } from '../../types';
import { useI18n, type AppLocale } from '../../i18n';
import Screen from '../../components/ui/Screen';
import ScreenHeader from '../../components/ui/ScreenHeader';
import Icon from '../../components/ui/Icon';
import { COLORS } from '../../constants/config';

const OPTIONS: Array<{ code: AppLocale; key: 'languageEs' | 'languageZh' | 'languageEn' }> = [
  { code: 'es', key: 'languageEs' },
  { code: 'en', key: 'languageEn' },
  { code: 'zh', key: 'languageZh' },
];

const LanguageSettingsScreen = () => {
  const navigation = useNavigation<StackNavigationProp<RootStackParamList, 'Language'>>();
  const { t, locale, setLocale } = useI18n();

  return (
    <Screen edges={['top', 'bottom']} style={styles.screen}>
      <ScreenHeader title={t.account.language} onBack={() => navigation.goBack()} />
      <View style={styles.content}>
        <View style={styles.intro}>
          <View style={styles.iconWrap}>
            <Icon name="globe-outline" size={24} color={COLORS.PRIMARY} />
          </View>
          <Text style={styles.hint}>{t.account.languageHint}</Text>
        </View>

        <View style={styles.list}>
          {OPTIONS.map((option, index) => {
            const selected = locale === option.code;
            return (
              <TouchableOpacity
                key={option.code}
                testID={`app-language-${option.code}`}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                style={[styles.row, index < OPTIONS.length - 1 && styles.rowBorder]}
                onPress={() => setLocale(option.code)}
              >
                <View>
                  <Text style={[styles.language, selected && styles.languageSelected]}>
                    {t.account[option.key]}
                  </Text>
                  <Text style={styles.code}>{option.code.toUpperCase()}</Text>
                </View>
                <Icon
                  name={selected ? 'checkmark-circle' : 'ellipse-outline'}
                  size={24}
                  color={selected ? COLORS.PRIMARY : COLORS.BORDER}
                />
              </TouchableOpacity>
            );
          })}
        </View>
      </View>
    </Screen>
  );
};

const styles = StyleSheet.create({
  screen: { backgroundColor: COLORS.BACKGROUND },
  content: { width: '100%', maxWidth: 560, alignSelf: 'center', padding: 20 },
  intro: { alignItems: 'center', paddingVertical: 28 },
  iconWrap: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.PRIMARY_SOFT,
    marginBottom: 12,
  },
  hint: { fontSize: 15, lineHeight: 22, textAlign: 'center', color: COLORS.TEXT_SECONDARY },
  list: {
    borderRadius: 18,
    backgroundColor: COLORS.CARD_BG,
    borderWidth: 1,
    borderColor: COLORS.BORDER,
    overflow: 'hidden',
  },
  row: {
    minHeight: 72,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: COLORS.BORDER },
  language: { fontSize: 16, fontWeight: '600', color: COLORS.TEXT_PRIMARY },
  languageSelected: { color: COLORS.PRIMARY_DARK },
  code: { marginTop: 4, fontSize: 11, letterSpacing: 1.2, color: COLORS.TEXT_TERTIARY },
});

export default LanguageSettingsScreen;
