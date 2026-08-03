export type ScannerResultSurfaceState = 'idle' | 'confident' | 'uncertain' | 'unknown';

export function scannerChromeVisibility(state: ScannerResultSurfaceState) {
  const confident = state === 'confident';
  return {
    showBottomTabs: !confident,
    showCamera: !confident,
    showDevelopmentLocation: !confident,
  };
}
