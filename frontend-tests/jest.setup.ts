jest.mock('react-native-reanimated', () => require('react-native-reanimated/mock'));

jest.mock('@expo/vector-icons', () => {
  const React = require('react');
  const { View } = require('react-native');
  const Ionicons = ({ name, ...props }: { name: string }) =>
    React.createElement(View, { ...props, accessibilityLabel: `icon-${name}` });
  Ionicons.glyphMap = {};
  return { Ionicons };
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
