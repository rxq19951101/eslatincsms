/**
 * 本文件为 Expo 应用入口：配置导航栈与底部标签导航。
 * 页面：Login / Register / Map / Scan / History / Account / Support / Session
 * 仅用于本地测试与演示。
 */

import { StatusBar } from 'expo-status-bar';
import React, { useState, useEffect } from 'react';
import { View, Text } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import LoginScreen from './screens/LoginScreen';
import RegisterScreen from './screens/RegisterScreen';
import MapScreen from './screens/MapScreen';
import ScanScreen from './screens/ScanScreen';
import HistoryScreen from './screens/HistoryScreen';
import AccountScreen from './screens/AccountScreen';
import SupportScreen from './screens/SupportScreen';
import SessionScreen from './screens/SessionScreen';

const Stack = createStackNavigator();
const Tab = createBottomTabNavigator();

// 主标签导航（已登录）
function MainTabs({
  user,
  onLogout,
  navigation: rootNavigation,
}: {
  user: { username: string; idTag: string };
  onLogout: () => void;
  navigation: any;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Tab.Navigator
      initialRouteName="Map"
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#007AFF',
          borderTopWidth: 0,
          elevation: 8,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.1,
          shadowRadius: 4,
          height: 60 + insets.bottom,
          paddingBottom: Math.max(insets.bottom, 8),
        },
        tabBarActiveTintColor: '#fff',
        tabBarInactiveTintColor: 'rgba(255, 255, 255, 0.6)',
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '600',
        },
        tabBarItemStyle: {
          paddingTop: 6,
        },
      }}
    >
      <Tab.Screen
        name="Support"
        options={{
          tabBarLabel: 'Soporte',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>🎧</Text>,
        }}
      >
        {(props) => <SupportScreen {...props} user={user} />}
      </Tab.Screen>
      <Tab.Screen
        name="Map"
        options={{
          tabBarLabel: 'Cargadores',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>🗺️</Text>,
        }}
      >
        {(props) => <MapScreen {...props} />}
      </Tab.Screen>
      <Tab.Screen
        name="Scan"
        options={{
          tabBarLabel: 'chargeway',
          tabBarIcon: ({ color }) => (
            <View style={{
              width: 56,
              height: 56,
              borderRadius: 28,
              backgroundColor: '#34c759',
              justifyContent: 'center',
              alignItems: 'center',
              marginTop: -20,
              borderWidth: 4,
              borderColor: '#fff',
            }}>
              <Text style={{ fontSize: 24 }}>📱</Text>
            </View>
          ),
          tabBarIconStyle: { marginTop: -10 - insets.bottom / 2 },
        }}
      >
        {(props) => <ScanScreen {...props} rootNavigation={rootNavigation} />}
      </Tab.Screen>
      <Tab.Screen
        name="History"
        options={{
          tabBarLabel: 'Historial',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>📜</Text>,
        }}
      >
        {(props) => <HistoryScreen {...props} />}
      </Tab.Screen>
      <Tab.Screen
        name="Account"
        options={{
          tabBarLabel: 'Cuenta',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>👤</Text>,
        }}
      >
        {(props) => <AccountScreen {...props} user={user} onLogout={onLogout} />}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

export default function App() {
  const [user, setUser] = useState<{ username: string; idTag: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 检查是否已登录
    AsyncStorage.getItem('current_user').then((data) => {
      if (data) {
        setUser(JSON.parse(data));
      }
      setLoading(false);
    });
  }, []);

  const handleLogin = (userData: { username: string; idTag: string }) => {
    setUser(userData);
  };

  const handleLogout = async () => {
    await AsyncStorage.removeItem('current_user');
    setUser(null);
  };

  if (loading) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <StatusBar style="auto" />
        <Stack.Navigator
        initialRouteName={user ? 'Main' : 'Login'}
        screenOptions={{
          headerShown: false,
        }}
      >
        {!user ? (
          // 未登录时的导航栈
          <>
            <Stack.Screen name="Login">
              {(props) => <LoginScreen {...props} onLogin={handleLogin} />}
            </Stack.Screen>
            <Stack.Screen name="Register" options={{ title: '注册' }}>
              {(props) => <RegisterScreen {...props} onLogin={handleLogin} />}
            </Stack.Screen>
          </>
        ) : (
          // 已登录时的导航栈
          <>
            <Stack.Screen name="Main">
              {(props) => <MainTabs {...props} user={user} onLogout={handleLogout} />}
            </Stack.Screen>
            <Stack.Screen
              name="Session"
              options={{
                headerShown: true,
                headerStyle: { backgroundColor: '#007AFF' },
                headerTintColor: '#fff',
                headerTitleStyle: { fontWeight: '600' },
                title: '充电会话',
              }}
            >
              {(props) => <SessionScreen {...props} user={user} />}
            </Stack.Screen>
          </>
        )}
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
