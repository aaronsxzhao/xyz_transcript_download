// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ScreenshotGallery from '../src/components/ScreenshotGallery';

let root: ReturnType<typeof createRoot>, node: HTMLDivElement;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {value: vi.fn(), configurable: true});
  node = document.createElement('div'); document.body.append(node);
  root = createRoot(node);
  act(() => root.render(<ScreenshotGallery images={[
    {src:'/first.png',alt:'First chart'}, {src:'/second.png',alt:'Second chart'},
  ]} initial={0} onClose={() => {}} />));
});
afterEach(() => {
  act(() => root.unmount()); node.remove(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
});
const dialog = () => document.querySelector('[role="dialog"]')!;
const image = () => dialog().querySelector('img')!;
function click(text: string) {
  act(() => [...dialog().querySelectorAll('button')].find(b => b.textContent === text)!.click());
}
it('offers a retry when an original never finishes loading', async () => {
  await act(async () => vi.advanceTimersByTimeAsync(30000));
  expect(dialog().textContent).toContain('Original image loading timed out');
  expect(dialog().querySelector('img')).toBeNull();
  click('Retry original');
  expect(image().getAttribute('src')).toBe('/first.png');
  act(() => image().dispatchEvent(new Event('load')));
  expect(dialog().textContent).not.toContain('timed out');
  expect(image().style.display).toBe('block');
});
it('gives the next image its own deadline and clears it after load', async () => {
  await act(async () => vi.advanceTimersByTimeAsync(25000));
  click('Next');
  await act(async () => vi.advanceTimersByTimeAsync(5000));
  expect(image().getAttribute('src')).toBe('/second.png');
  expect(dialog().textContent).toContain('Loading original image');
  act(() => image().dispatchEvent(new Event('load')));
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(dialog().querySelector('[role="alert"]')).toBeNull();
  expect(image().style.display).toBe('block');
});
it('lets users continue to the next image after a download error', () => {
  act(() => image().dispatchEvent(new Event('error')));
  expect(dialog().textContent).toContain('Original image could not load');
  click('Next');
  expect(image().getAttribute('src')).toBe('/second.png');
  act(() => image().dispatchEvent(new Event('load')));
  expect(image().style.display).toBe('block');
});
