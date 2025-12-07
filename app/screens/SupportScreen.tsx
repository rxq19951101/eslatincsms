/**
 * 本文件为客服支持页面：提供帮助和联系客服。
 * 仅用于本地测试与演示。
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { API_ENDPOINTS } from '../config';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

type SupportScreenProps = {
  navigation: any;
  user?: { username: string; idTag: string };
};

export default function SupportScreen({ navigation, user }: SupportScreenProps) {
  const insets = useSafeAreaInsets();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const handleSendMessage = async () => {
    if (!message.trim()) {
      Alert.alert('提示', '请输入您的消息');
      return;
    }

    if (!user) {
      Alert.alert('错误', '请先登录');
      return;
    }

    try {
      setSending(true);
      const res = await fetch(API_ENDPOINTS.messages, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userId: user.idTag,
          username: user.username,
          message: message.trim(),
        }),
      });

      if (res.ok) {
        Alert.alert('已发送', '您的消息已发送给客服，我们会尽快回复您', [
          { text: '确定', onPress: () => setMessage('') }
        ]);
      } else {
        Alert.alert('错误', '发送失败，请稍后重试');
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      Alert.alert('错误', '网络错误，请检查连接');
    } finally {
      setSending(false);
    }
  };

  const quickActions = [
    {
      icon: '📞',
      title: '电话客服',
      subtitle: '400-123-4567',
      onPress: () => Alert.alert('拨打电话', '是否拨打 400-123-4567？'),
    },
    {
      icon: '💬',
      title: '在线客服',
      subtitle: '工作时间：9:00-21:00',
      onPress: () => Alert.alert('在线客服', '正在连接客服...'),
    },
    {
      icon: '📧',
      title: '邮件反馈',
      subtitle: 'support@ocpp.local',
      onPress: () => Alert.alert('邮件反馈', '请发送邮件至 support@ocpp.local'),
    },
    {
      icon: '❓',
      title: '常见问题',
      subtitle: '查看帮助文档',
      onPress: () => Alert.alert('常见问题', '常见问题页面开发中...'),
    },
  ];

  return (
    <SafeAreaView style={[styles.safeArea, { paddingTop: insets.top }]} edges={['top', 'left', 'right']}>
      <ScrollView
        style={styles.container}
        contentContainerStyle={{ paddingBottom: Math.max(insets.bottom, 24) }}
      >
      <View style={styles.header}>
        <Text style={styles.headerTitle}>客服支持</Text>
        <Text style={styles.headerSubtitle}>我们随时为您服务</Text>
      </View>

      {/* 快捷操作 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>联系方式</Text>
        <View style={styles.quickActions}>
          {quickActions.map((action, index) => (
            <TouchableOpacity
              key={index}
              style={styles.actionCard}
              onPress={action.onPress}
            >
              <Text style={styles.actionIcon}>{action.icon}</Text>
              <Text style={styles.actionTitle}>{action.title}</Text>
              <Text style={styles.actionSubtitle}>{action.subtitle}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* 消息发送 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>发送消息</Text>
        <TextInput
          style={styles.messageInput}
          placeholder="请输入您的问题或建议..."
          value={message}
          onChangeText={setMessage}
          multiline
          numberOfLines={4}
          textAlignVertical="top"
        />
        <TouchableOpacity 
          style={[styles.sendButton, sending && styles.sendButtonDisabled]} 
          onPress={handleSendMessage}
          disabled={sending}
        >
          {sending ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.sendButtonText}>发送</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* 常见问题 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>常见问题</Text>
        <View style={styles.faqList}>
          <TouchableOpacity style={styles.faqItem}>
            <Text style={styles.faqIcon}>❓</Text>
            <View style={styles.faqContent}>
              <Text style={styles.faqTitle}>如何开始充电？</Text>
              <Text style={styles.faqAnswer}>
                在主页面搜索或扫码找到充电桩，点击开始充电即可。
              </Text>
            </View>
          </TouchableOpacity>

          <TouchableOpacity style={styles.faqItem}>
            <Text style={styles.faqIcon}>❓</Text>
            <View style={styles.faqContent}>
              <Text style={styles.faqTitle}>充电费用如何计算？</Text>
              <Text style={styles.faqAnswer}>
                费用按电量（kWh）计费，具体价格请查看充电桩信息。
              </Text>
            </View>
          </TouchableOpacity>

          <TouchableOpacity style={styles.faqItem}>
            <Text style={styles.faqIcon}>❓</Text>
            <View style={styles.faqContent}>
              <Text style={styles.faqTitle}>如何停止充电？</Text>
              <Text style={styles.faqAnswer}>
                在充电会话页面点击停止充电按钮即可。
              </Text>
            </View>
          </TouchableOpacity>
        </View>
      </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#fff',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#333',
    marginBottom: 4,
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#666',
  },
  section: {
    backgroundColor: '#fff',
    marginTop: 16,
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 16,
  },
  quickActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  actionCard: {
    width: '48%',
    backgroundColor: '#f9f9f9',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  actionIcon: {
    fontSize: 32,
    marginBottom: 8,
  },
  actionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  actionSubtitle: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
  },
  messageInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    minHeight: 100,
    backgroundColor: '#f9f9f9',
    marginBottom: 12,
  },
  sendButton: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#999',
    opacity: 0.6,
  },
  sendButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  faqList: {
    marginTop: 8,
  },
  faqItem: {
    flexDirection: 'row',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  faqIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  faqContent: {
    flex: 1,
  },
  faqTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  faqAnswer: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
  },
});

