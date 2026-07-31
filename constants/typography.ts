import {
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import {
  SourceSans3_400Regular,
  SourceSans3_500Medium,
  SourceSans3_600SemiBold,
  SourceSans3_700Bold,
  SourceSans3_800ExtraBold,
  SourceSans3_900Black,
} from '@expo-google-fonts/source-sans-3';
import type { FontSource } from 'expo-font';
import type { TextStyle } from 'react-native';

export const FONT_OPTIONS = {
  manrope: {
    families: {
      regular: 'GreenBinManrope-Regular',
      medium: 'GreenBinManrope-Medium',
      semiBold: 'GreenBinManrope-SemiBold',
      bold: 'GreenBinManrope-Bold',
      extraBold: 'GreenBinManrope-ExtraBold',
      black: 'GreenBinManrope-ExtraBold',
    },
    sources: {
      regular: Manrope_400Regular,
      medium: Manrope_500Medium,
      semiBold: Manrope_600SemiBold,
      bold: Manrope_700Bold,
      extraBold: Manrope_800ExtraBold,
      black: Manrope_800ExtraBold,
    },
  },
  sourceSans3: {
    families: {
      regular: 'GreenBinSourceSans3-Regular',
      medium: 'GreenBinSourceSans3-Medium',
      semiBold: 'GreenBinSourceSans3-SemiBold',
      bold: 'GreenBinSourceSans3-Bold',
      extraBold: 'GreenBinSourceSans3-ExtraBold',
      black: 'GreenBinSourceSans3-Black',
    },
    sources: {
      regular: SourceSans3_400Regular,
      medium: SourceSans3_500Medium,
      semiBold: SourceSans3_600SemiBold,
      bold: SourceSans3_700Bold,
      extraBold: SourceSans3_800ExtraBold,
      black: SourceSans3_900Black,
    },
  },
} as const;

export type FontOption = keyof typeof FONT_OPTIONS;

// Change either value here to switch the corresponding text role app-wide.
export const TYPOGRAPHY_CONFIG = {
  primary: 'manrope',
  secondary: 'sourceSans3',
} as const satisfies Record<'primary' | 'secondary', FontOption>;

const primaryFont = FONT_OPTIONS[TYPOGRAPHY_CONFIG.primary];
const secondaryFont = FONT_OPTIONS[TYPOGRAPHY_CONFIG.secondary];

function addFontSources(
  sources: Record<string, FontSource>,
  font: (typeof FONT_OPTIONS)[FontOption]
) {
  for (const weight of Object.keys(font.families) as (keyof typeof font.families)[]) {
    sources[font.families[weight]] = font.sources[weight];
  }
}

export const FONT_SOURCES: Record<string, FontSource> = {};
addFontSources(FONT_SOURCES, primaryFont);
addFontSources(FONT_SOURCES, secondaryFont);

function textStyle(fontFamily: string): Pick<TextStyle, 'fontFamily' | 'fontWeight'> {
  return {
    fontFamily,
    fontWeight: 'normal',
  };
}

export const PRIMARY_TEXT_STYLES = {
  header: textStyle(primaryFont.families.black),
  title: textStyle(primaryFont.families.extraBold),
  button: textStyle(primaryFont.families.bold),
  label: textStyle(primaryFont.families.semiBold),
  tab: textStyle(primaryFont.families.bold),
  loading: textStyle(primaryFont.families.extraBold),
} as const;

export const SECONDARY_TEXT_STYLES = {
  regular: textStyle(secondaryFont.families.regular),
  medium: textStyle(secondaryFont.families.medium),
  semiBold: textStyle(secondaryFont.families.semiBold),
  bold: textStyle(secondaryFont.families.bold),
  extraBold: textStyle(secondaryFont.families.extraBold),
  black: textStyle(secondaryFont.families.black),
} as const;
