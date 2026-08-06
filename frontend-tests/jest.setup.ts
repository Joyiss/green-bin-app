jest.mock('react-native-reanimated', () => require('react-native-reanimated/mock'));

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('@expo/vector-icons', () => {
  const React = require('react');
  const { View } = require('react-native');
  const Ionicons = ({ name, ...props }: { name: string }) =>
    React.createElement(View, { ...props, accessibilityLabel: `icon-${name}` });
  const MaterialCommunityIcons = ({ name, ...props }: { name: string }) =>
    React.createElement(View, { ...props, accessibilityLabel: `icon-${name}` });
  Ionicons.glyphMap = {};
  MaterialCommunityIcons.glyphMap = {};
  return { Ionicons, MaterialCommunityIcons };
});

jest.mock('@expo/vector-icons/FontAwesome', () => {
  const React = require('react');
  const { View } = require('react-native');
  const FontAwesome = ({ name, ...props }: { name: string }) =>
    React.createElement(View, { ...props, accessibilityLabel: `icon-${name}` });
  FontAwesome.glyphMap = {};
  return FontAwesome;
});

jest.mock('@/constants/typography', () => ({
  FREDOKA_TEXT_STYLES: {
    medium: { fontFamily: 'Fredoka-Medium', fontWeight: 'normal' },
    semiBold: { fontFamily: 'Fredoka-SemiBold', fontWeight: 'normal' },
  },
  INTER_TEXT_STYLES: {
    regular: { fontFamily: 'Inter-Regular', fontWeight: 'normal' },
    medium: { fontFamily: 'Inter-Medium', fontWeight: 'normal' },
    semiBold: { fontFamily: 'Inter-SemiBold', fontWeight: 'normal' },
  },
  MANROPE_TEXT_STYLES: new Proxy({}, {
    get: (_, weight) => ({ fontFamily: `GreenBinManrope-${String(weight)}`, fontWeight: 'normal' }),
  }),
  PRIMARY_TEXT_STYLES: new Proxy({}, { get: () => ({}) }),
  SECONDARY_TEXT_STYLES: new Proxy({}, { get: () => ({}) }),
}));
