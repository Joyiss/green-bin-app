import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import * as NavigationBar from 'expo-navigation-bar';
import { Stack, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect } from 'react';
import { AppState, InteractionManager, Platform } from 'react-native';
import 'react-native-reanimated';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { useColorScheme } from '@/hooks/use-color-scheme';

export const unstable_settings = {
  anchor: '(tabs)',
};

function useAndroidNavigationBar(isScanScreen: boolean) {
  const updateNavigationBar = useCallback(() => {
    if (Platform.OS !== 'android') {
      return;
    }

    NavigationBar.setStyle('light');
    NavigationBar.setVisibilityAsync(isScanScreen ? 'hidden' : 'visible').catch(() => {});
  }, [isScanScreen]);

  useEffect(() => {
    updateNavigationBar();
    const navigationBarTask = InteractionManager.runAfterInteractions(updateNavigationBar);

    return () => {
      navigationBarTask.cancel();
    };
  }, [updateNavigationBar]);

  useEffect(() => {
    if (Platform.OS !== 'android') {
      return;
    }

    const navigationBarSubscription = NavigationBar.addVisibilityListener(({ visibility }) => {
      const expectedVisibility = isScanScreen ? 'hidden' : 'visible';
      if (visibility !== expectedVisibility) {
        updateNavigationBar();
      }
    });
    const appStateSubscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'active') {
        updateNavigationBar();
      }
    });

    return () => {
      navigationBarSubscription.remove();
      appStateSubscription.remove();
    };
  }, [isScanScreen, updateNavigationBar]);
}

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const segments = useSegments();
  const isScanScreen = segments.length === 1 && segments[0] === '(tabs)';
  const statusBarStyle = isScanScreen ? 'light' : 'dark';
  useAndroidNavigationBar(isScanScreen);

  return (
    <GestureHandlerRootView style={{ backgroundColor: '#F3F1EE', flex: 1 }}>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <StatusBar style={statusBarStyle} />
        <Stack
          screenOptions={{
            navigationBarColor: 'transparent',
            navigationBarHidden: isScanScreen,
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
