import { fireEvent, render, within } from '@testing-library/react-native';
import { Linking, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';

import type { ResultSheetPresentation } from '../app/result-sheet-model';
import { ConfidentResultScreen } from '../components/confident-result-screen';
import { ResultFeedback } from '../components/result-feedback';

const presentation: ResultSheetPresentation = {
  action: 'Drop off',
  bestOption: 'Take this item to River County Device Recovery for local drop-off.',
  destinationLabel: 'River County Device Recovery',
  evidence: {
    summary: 'A local provider lists consumer electronics drop-off services.',
    rows: [
      { label: 'Item identified', value: 'Portable speaker' },
      { label: 'Category or material', value: 'Electronics' },
      { label: 'Local route found', value: 'Schedule a drop-off with River County Device Recovery.' },
      { label: 'Confidence', value: 'High' },
    ],
  },
  facts: [
    { label: 'Appointment', value: 'Required' },
    { label: 'Preparation', value: 'Visit the provider.' },
    { label: 'Location required', value: 'Yes' },
  ],
  item: 'Portable speaker',
  keyQualifier: 'Appointment required',
  preparationSteps: [
    { title: 'Keep the device intact' },
  ],
  primaryAction: { behavior: 'nearby', label: 'Find Drop-Off Options' },
  references: [
    {
      description: 'Accepts small consumer electronics by appointment.',
      domain: 'provider.example',
      role: 'Local service provider',
      title: 'River County Device Recovery',
      url: 'http://provider.example/takeback?from=app',
    },
  ],
  status: [
    { label: 'Category', value: 'Electronics' },
    { label: 'Guidance', value: 'Local guidance found' },
    { label: 'Location', value: 'River City, Ohio' },
  ],
  steps: [
    { title: 'Schedule the drop-off', body: 'Confirm current hours before visiting.' },
    { title: 'Bring the item', body: 'Follow the provider\'s electronics instructions.' },
  ],
  warnings: [],
};

async function renderScreen(overrides: Partial<ResultSheetPresentation> = {}) {
  const onChangeItem = jest.fn();
  const onClose = jest.fn();
  const onGuidanceAnswer = jest.fn();
  const onItemAnswer = jest.fn();
  const onPrimaryAction = jest.fn();
  const view = await render(
    <ConfidentResultScreen
      bottomInset={34}
      onChangeItem={onChangeItem}
      onClose={onClose}
      onPrimaryAction={onPrimaryAction}
      presentation={{ ...presentation, ...overrides }}
      topInset={44}>
      <ResultFeedback
        guidanceAnswer={null}
        itemAnswer={null}
        onGuidanceAnswer={onGuidanceAnswer}
        onItemAnswer={onItemAnswer}
        showGuidanceQuestion
      />
    </ConfidentResultScreen>,
  );
  return { onChangeItem, onClose, onGuidanceAnswer, onItemAnswer, onPrimaryAction, view };
}

function renderedTextNodes(value: unknown): { props: { style?: unknown }; type?: unknown }[] {
  if (Array.isArray(value)) return value.flatMap(renderedTextNodes);
  if (!value || typeof value !== 'object') return [];
  const node = value as {
    children?: unknown;
    props: { style?: unknown };
    type?: unknown;
  };
  return [
    ...(node.type === 'Text' ? [node] : []),
    ...renderedTextNodes(node.children),
  ];
}

test('result fills the usable screen below the safe area', async () => {
  const { view } = await renderScreen();
  const overlay = StyleSheet.flatten(view.getByTestId('confident-result-screen').props.style);
  const surface = StyleSheet.flatten(view.getByTestId('confident-result-surface').props.style);

  expect(overlay.position).toBe('absolute');
  expect(overlay.top).toBe(0);
  expect(overlay.bottom).toBe(0);
  expect(surface.flex).toBe(1);
  expect(view.getByLabelText('Disposal guidance details')).toBeTruthy();
});

test('uses only loaded Fredoka or Inter faces and keeps compact sizes', async () => {
  const { view } = await renderScreen();
  const textNodes = renderedTextNodes(view.toJSON());
  const allowedFamilies = new Set([
    'Fredoka-Medium',
    'Fredoka-SemiBold',
    'Inter-Regular',
    'Inter-Medium',
    'Inter-SemiBold',
  ]);

  for (const node of textNodes) {
    const style = StyleSheet.flatten(node.props.style) as TextStyle;
    expect(style.fontSize ?? 0).toBeLessThanOrEqual(30);
    expect(allowedFamilies.has(String(style.fontFamily))).toBe(true);
    expect(['400', '500', '600']).toContain(style.fontWeight);
  }
});

test('uses Fredoka for headings and Inter for body text, metadata, and buttons', async () => {
  const { view } = await renderScreen();

  expect(StyleSheet.flatten(view.getByText('Disposal Details').props.style).fontFamily).toBe('Fredoka-SemiBold');
  expect(StyleSheet.flatten(view.getByTestId('recognized-item').props.style).fontFamily).toBe('Fredoka-Medium');
  expect(StyleSheet.flatten(view.getByTestId('summary-action').props.style).fontFamily).toBe('Fredoka-SemiBold');
  expect(StyleSheet.flatten(view.getByText('What to do').props.style).fontFamily).toBe('Fredoka-Medium');
  expect(StyleSheet.flatten(view.getByTestId('summary-description').props.style).fontFamily).toBe('Inter-Regular');
  expect(StyleSheet.flatten(view.getByTestId('compact-item-metadata').props.style).fontFamily).toBe('Inter-Regular');
  expect(StyleSheet.flatten(view.getByText('A local provider lists consumer electronics drop-off services.').props.style).fontFamily).toBe('Inter-Regular');
  expect(StyleSheet.flatten(view.getByText('Find Drop-Off Options').props.style).fontFamily).toBe('Inter-SemiBold');
});

test('summary card uses action, destination, and one compact qualifier', async () => {
  const { view } = await renderScreen();
  const card = within(view.getByTestId('primary-summary-card'));

  expect(card.getByLabelText('icon-refresh-outline')).toBeTruthy();
  expect(card.getByText('Drop off')).toBeTruthy();
  expect(card.getByText('River County Device Recovery')).toBeTruthy();
  expect(card.getByText('Appointment required')).toBeTruthy();
  expect(card.queryByText('Take this item to River County Device Recovery for local drop-off.')).toBeNull();
  expect(card.queryByText('Preparation')).toBeNull();
  expect(card.queryByText('Location required')).toBeNull();
  expect(view.queryByText('Area')).toBeNull();
  expect(StyleSheet.flatten(view.getByTestId('primary-summary-card').props.style).borderColor).toBe('#E7E1D9');
});

test('body descriptions use regular weight and item metadata stays minimal', async () => {
  const { view } = await renderScreen();
  const summary = view.getByTestId('summary-description');
  const metadata = view.getByTestId('compact-item-metadata');

  expect(StyleSheet.flatten(summary.props.style).fontWeight).toBe('400');
  expect(metadata.props.children).toBe('Electronics \u2022 River City');
  expect(view.queryByText(/Local guidance/i)).toBeNull();
});

test('What to do and its first instruction follow the summary near the top', async () => {
  const { view } = await renderScreen();
  const tree = JSON.stringify(view.toJSON());

  expect(tree.indexOf('primary-summary-card')).toBeLessThan(tree.indexOf('what-to-do-section'));
  expect(tree.indexOf('what-to-do-section')).toBeLessThan(tree.indexOf('first-guidance-step'));
  expect(view.getByText('Keep the device intact')).toBeTruthy();
});

test('references expand, collapse, and open the original source URL', async () => {
  const openUrl = jest.spyOn(Linking, 'openURL').mockResolvedValueOnce(true);
  const { view } = await renderScreen();
  const collapsed = view.getByRole('button', { name: 'References' });

  expect(collapsed.props.accessibilityState).toEqual({ expanded: false });
  expect(view.getByLabelText('icon-book-outline')).toBeTruthy();
  expect(view.queryByText('provider.example')).toBeNull();
  await fireEvent.press(collapsed);
  expect(view.getByText('provider.example')).toBeTruthy();
  await fireEvent.press(
    view.getByRole('link', { name: 'Open source: River County Device Recovery' }),
  );
  expect(openUrl).toHaveBeenCalledWith('http://provider.example/takeback?from=app');
  await fireEvent.press(view.getByRole('button', { name: 'References' }));
  expect(view.queryByText('provider.example')).toBeNull();
});

test('feedback, close, Change Item, and Nearby action callbacks remain intact', async () => {
  const result = await renderScreen();
  const { view } = result;

  await fireEvent.press(view.getByRole('button', { name: 'Close scan result' }));
  await fireEvent.press(view.getByRole('button', { name: 'Change Item' }));
  await fireEvent.press(view.getByRole('button', { name: 'Item identified correctly: yes' }));
  await fireEvent.press(view.getByRole('button', { name: 'Disposal guidance helpful: no' }));
  await fireEvent.press(view.getByRole('button', { name: 'Find Drop-Off Options' }));

  expect(result.onClose).toHaveBeenCalledTimes(1);
  expect(result.onChangeItem).toHaveBeenCalledTimes(1);
  expect(result.onItemAnswer).toHaveBeenCalledWith(true);
  expect(result.onGuidanceAnswer).toHaveBeenCalledWith(false);
  expect(result.onPrimaryAction).toHaveBeenCalledTimes(1);
});

test('instruction primary actions scroll without changing Nearby behavior', async () => {
  const result = await renderScreen({
    primaryAction: { behavior: 'scroll_steps', label: 'View Curbside Instructions' },
  });
  await fireEvent.press(
    result.view.getByRole('button', { name: 'View Curbside Instructions' }),
  );
  expect(result.onPrimaryAction).not.toHaveBeenCalled();
});

test('unsupported warnings and primary actions remain hidden', async () => {
  const { view } = await renderScreen({ facts: [], primaryAction: null, warnings: [] });
  expect(view.queryByText('Before you go')).toBeNull();
  expect(view.queryByRole('button', { name: 'Find Drop-Off Options' })).toBeNull();
});

test('shows the explicit message when preparation is unnecessary', async () => {
  const { view } = await renderScreen({
    noPreparationMessage: 'No special preparation needed.',
    preparationSteps: [],
    steps: [],
  });
  expect(view.getByTestId('no-preparation-section')).toBeTruthy();
  expect(view.getByText('No special preparation needed.')).toBeTruthy();
});

test('Before you go shows warnings or preparation details without the old heading', async () => {
  const { view } = await renderScreen({
    keyQualifier: 'Appointment required',
    warnings: ['Keep exposed battery terminals covered.'],
  });
  expect(view.queryByText('Important note')).toBeNull();
  expect(view.getByText('Before you go')).toBeTruthy();
  expect(view.getByText('Keep exposed battery terminals covered.')).toBeTruthy();
  expect(view.getAllByLabelText('icon-warning-outline')).toHaveLength(1);
});

test('summary repeats, route steps, and unrelated restriction lists are omitted', async () => {
  const { view } = await renderScreen({
    bestOption: 'Take this item to River County Device Recovery for local drop-off.',
    keyQualifier: 'Paid electronics collection',
    preparationSteps: [],
    steps: [{ title: 'Take this item to River County Device Recovery for local drop-off' }],
    warnings: [
      'Take this item to River County Device Recovery for local drop-off.',
      'The center does not accept televisions, refrigerators, or large appliances listed as excluded.',
    ],
  });
  expect(view.queryByText('What to do')).toBeNull();
  expect(view.queryByText('Before you go')).toBeNull();
  expect(view.queryAllByText('Take this item to River County Device Recovery for local drop-off.')).toHaveLength(0);
});

test('step badges use the shared cream surface and dark neutral numbers', async () => {
  const { view } = await renderScreen();
  const number = view.getByText('1');
  const badge = number.parent;
  expect(StyleSheet.flatten(badge?.props.style).backgroundColor).toBe('#F4F1EC');
  expect(StyleSheet.flatten(number.props.style).color).toBe('#413D38');
});

test('cleans raw markdown from displayed reasoning and source descriptions', async () => {
  const { view } = await renderScreen({
    evidence: {
      summary: '**Portable speaker** matched [electronics guidance](https://example.com).',
      rows: [
        { label: 'Item identified', value: '**Portable speaker**' },
        { label: 'Confidence', value: 'Medium' },
      ],
    },
    references: [
      {
        description: '- Accepts **small devices** by appointment.',
        domain: 'provider.example',
        role: 'Local service provider',
        title: 'River County Device Recovery',
        url: 'http://provider.example/takeback?from=app',
      },
    ],
  });
  expect(view.getByText('Portable speaker matched electronics guidance.')).toBeTruthy();
  expect(view.queryByText(/\*\*/)).toBeNull();
  await fireEvent.press(view.getByRole('button', { name: 'References' }));
  expect(view.getByText('Accepts small devices by appointment.')).toBeTruthy();
});

test('route icons generalize across common disposal outcomes', async () => {
  const cases = [
    ['Trash', 'icon-trash-outline'],
    ['Compost', 'icon-leaf-outline'],
    ['Donate or reuse', 'icon-gift-outline'],
    ['Special handling', 'icon-warning-outline'],
  ];
  for (const [action, icon] of cases) {
    const { view } = await renderScreen({ action });
    expect(within(view.getByTestId('primary-summary-card')).getByLabelText(icon)).toBeTruthy();
  }
});
