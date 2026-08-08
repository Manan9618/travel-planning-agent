import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement matchMedia; useTheme.ts calls it to detect the
// system color-scheme preference, so any test rendering ThemeToggle (or
// anything containing it, like Header) needs this standard shim.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}
