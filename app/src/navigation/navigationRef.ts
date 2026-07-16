import { createNavigationContainerRef } from '@react-navigation/native';
import type { RootStackParamList } from '../types';

export const navigationRef = createNavigationContainerRef<RootStackParamList>();

export function navigateToLogin() {
  if (navigationRef.isReady()) {
    navigationRef.reset({
      index: 0,
      routes: [{ name: 'Welcome' }],
    });
  }
}
