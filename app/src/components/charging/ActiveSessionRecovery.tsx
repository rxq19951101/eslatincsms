import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useAppDispatch, useAppSelector } from '../../hooks/useRedux';
import { restoreActiveSession } from '../../store/slices/chargingSlice';
import { navigationRef } from '../../navigation/navigationRef';

/**
 * Runs once for each authenticated login. Recovery is deliberately read-only:
 * polling and this gate can only call GET /charging/active, never POST /start.
 */
const ActiveSessionRecovery = () => {
  const dispatch = useAppDispatch();
  const { isAuthenticated, isInitialized, user } = useAppSelector((state) => state.auth);
  const { activeSession, recoveryChecked } = useAppSelector((state) => state.charging);
  const attemptedUser = useRef<string | null>(null);
  const navigatedSession = useRef<string | null>(null);
  const appState = useRef<AppStateStatus>(AppState.currentState);
  const authRef = useRef({ isAuthenticated, isInitialized, userId: user?.id });
  const [recoveredSessionId, setRecoveredSessionId] = useState<string | null>(null);

  authRef.current = { isAuthenticated, isInitialized, userId: user?.id };

  const recover = useCallback(() => {
    const auth = authRef.current;
    if (!auth.isInitialized || !auth.isAuthenticated || !auth.userId) return;

    const userId = auth.userId;
    void dispatch(restoreActiveSession()).then((action) => {
      if (authRef.current.userId !== userId || action.meta.requestStatus !== 'fulfilled') return;
      const recovered = action.payload as { id?: string } | null | undefined;
      setRecoveredSessionId(recovered?.id ?? null);
    });
  }, [dispatch]);

  useEffect(() => {
    if (!isInitialized || !isAuthenticated || !user?.id) {
      attemptedUser.current = null;
      navigatedSession.current = null;
      setRecoveredSessionId(null);
      return;
    }
    if (attemptedUser.current === user.id) return;
    attemptedUser.current = user.id;
    recover();
  }, [isAuthenticated, isInitialized, recover, user?.id]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      const returningToForeground = appState.current !== 'active' && nextState === 'active';
      appState.current = nextState;
      if (returningToForeground) recover();
    });
    return () => subscription.remove();
  }, [recover]);

  useEffect(() => {
    if (!recoveryChecked || !activeSession || recoveredSessionId !== activeSession.id) return;
    if (navigatedSession.current === activeSession.id) return;

    const openRecoveredSession = () => {
      if (!navigationRef.isReady()) return false;
      const current = navigationRef.getCurrentRoute();
      const currentSessionId = current?.name === 'ChargingProcess'
        ? (current.params as { sessionId?: string } | undefined)?.sessionId
        : undefined;
      if (current?.name !== 'ChargingProcess' || currentSessionId !== activeSession.id) {
        navigationRef.navigate('ChargingProcess', { sessionId: activeSession.id });
      }
      navigatedSession.current = activeSession.id;
      return true;
    };

    if (openRecoveredSession()) return;
    const timer = setTimeout(openRecoveredSession, 0);
    return () => clearTimeout(timer);
  }, [activeSession, recoveredSessionId, recoveryChecked]);

  return null;
};

export default ActiveSessionRecovery;
