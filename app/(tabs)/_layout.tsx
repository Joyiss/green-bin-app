import { Tabs } from 'expo-router';
import React from 'react';

import { BottomNavBar } from '@/components/bottom-nav-bar';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
      }}
      tabBar={(props) => <BottomNavBar {...props} />}>
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
