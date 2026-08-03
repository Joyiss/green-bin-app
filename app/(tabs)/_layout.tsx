import { Tabs } from 'expo-router';
import React from 'react';

import { BottomNavBar } from '@/components/bottom-nav-bar';
import {
  TabBarVisibilityProvider,
  useTabBarVisibility,
} from '@/components/tab-bar-visibility';

function TabNavigator() {
  const { hidden } = useTabBarVisibility();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
      }}
      tabBar={(props) => hidden ? null : <BottomNavBar {...props} />}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Scanner',
        }}
      />
      <Tabs.Screen
        name="nearby"
        options={{
          title: 'Nearby',
        }}
      />
      <Tabs.Screen
        name="scans"
        options={{
          title: 'Scans',
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
        }}
      />
    </Tabs>
  );
}

export default function TabLayout() {
  return (
    <TabBarVisibilityProvider>
      <TabNavigator />
    </TabBarVisibilityProvider>
  );
}
