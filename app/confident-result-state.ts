export type ScannerResultSurfaceState = 'idle' | 'confident' | 'uncertain' | 'unknown';

export function scannerChromeVisibility(state: ScannerResultSurfaceState) {
  const confident = state === 'confident';
  return {
    showBottomTabs: !confident,
    // Keep the captured Scan screen mounted as the backdrop for the draggable result sheet.
    showCamera: true,
    showDevelopmentLocation: !confident,
  };
}
