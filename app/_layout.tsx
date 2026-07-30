import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import * as NavigationBar from 'expo-navigation-bar';
import { Stack, usePathname, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect } from 'react';
import { AppState, InteractionManager, Platform } from 'react-native';
import 'react-native-reanimated';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { useColorScheme } from '@/hooks/use-color-scheme';

export const unstable_settings = {
  anchor: '(tabs)',
};

function useHiddenNavigationBar() {
  const pathname = usePathname();

  const hideNavigationBar = useCallback(() => {
    if (Platform.OS !== 'android') {
      return;
    }

    NavigationBar.setVisibilityAsync('hidden').catch(() => {});
  }, []);

  useEffect(() => {
    hideNavigationBar();
    const navigationBarTask = InteractionManager.runAfterInteractions(hideNavigationBar);

    return () => {
      navigationBarTask.cancel();
    };
  }, [hideNavigationBar, pathname]);

  useEffect(() => {
    if (Platform.OS !== 'android') {
      return;
    }

    const navigationBarSubscription = NavigationBar.addVisibilityListener(({ visibility }) => {
      if (visibility === 'visible') {
        hideNavigationBar();
      }
    });
    const appStateSubscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'active') {
        hideNavigationBar();
      }
    });

    return () => {
      navigationBarSubscription.remove();
      appStateSubscription.remove();
    };
  }, [hideNavigationBar]);
}

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const segments = useSegments();
  const isScanScreen = segments.length === 1 && segments[0] === '(tabs)';
  const statusBarStyle = isScanScreen ? 'light' : 'dark';
  useHiddenNavigationBar();

  return (
    <GestureHandlerRootView style={{ backgroundColor: '#F3F1EE', flex: 1 }}>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <StatusBar style={statusBarStyle} />
        <Stack
          screenOptions={{
            navigationBarColor: 'transparent',
            navigationBarHidden: true,
            navigationBarTranslucent: true,
            statusBarStyle: 'dark',
          }}>
          <Stack.Screen
            name="(tabs)"
            options={{
              headerShown: false,
              statusBarBackgroundColor: 'transparent',
              statusBarStyle,
              statusBarTranslucent: true,
            }}
          />
          <Stack.Screen
            name="recent-scan/[id]"
            options={{
              headerShown: false,
              presentation: 'modal',
            }}
          />
        </Stack>
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}
