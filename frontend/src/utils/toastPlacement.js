export const TOAST_POSITION_KEY = "sentriface.toastPosition.v1";
// Toasts sit above a dialog's dimmed backdrop but below the dialog itself (see sentriface-interface.css).
export const TOAST_Z_INDEX = 200;
export const EDGE = 16;
const DEFAULT_TOP = 84;
const NARROW_TOP = 72;
const WIDTH = 440;
const MIN_GUTTER = 280;
export const NARROW_WIDTH = 576;

export const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));

export function readSavedToastPosition(storage = window.localStorage) {
  try {
    const value = JSON.parse(storage.getItem(TOAST_POSITION_KEY));
    if (value && Number.isFinite(value.x) && Number.isFinite(value.y)) {
      return { x: clamp(value.x, 0, 1), y: clamp(value.y, 0, 1) };
    }
  } catch {
    // An unreadable saved position falls back to the default.
  }
  return null;
}

function intersects(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

// Saved positions are shares of the free space, so the stack stays on screen when the window is resized.
export function toastPositionFromRect({ left, top, width, height }, viewport) {
  const x = (left - EDGE) / Math.max(1, viewport.width - width - EDGE * 2);
  const y = top + height / 2 < viewport.height / 2 ? top / viewport.height : (top + height) / viewport.height;
  return { x: clamp(x, 0, 1), y: clamp(y, 0, 1) };
}

export function placeToastStack({ viewport, saved, stackHeight, dialogs = [] }) {
  const { width: vw, height: vh } = viewport;
  const narrow = vw < NARROW_WIDTH;
  const width = Math.min(WIDTH, vw - EDGE * 2);
  const height = stackHeight;
  const clampTop = (top) => clamp(top, EDGE / 2, vh - EDGE / 2 - height);
  let left = vw - EDGE - width;
  let top = narrow ? NARROW_TOP : DEFAULT_TOP;
  if (saved) {
    if (!narrow) left = EDGE + saved.x * Math.max(0, vw - width - EDGE * 2);
    top = clampTop(saved.y < 0.5 ? saved.y * vh : saved.y * vh - height);
  }
  const home = { left, top, width, narrow, dialog: false };
  if (!dialogs.length) return home;
  const box = (p) => ({ left: p.left, right: p.left + p.width, top: p.top, bottom: p.top + height });
  const clear = (p) => dialogs.every((dialog) => !intersects(box(p), dialog));
  if (clear(home)) return { ...home, dialog: true };
  const union = dialogs.reduce((all, d) => ({
    left: Math.min(all.left, d.left),
    right: Math.max(all.right, d.right),
    top: Math.min(all.top, d.top),
    bottom: Math.max(all.bottom, d.bottom),
  }));
  const rightGutter = vw - union.right - EDGE * 2;
  const leftGutter = union.left - EDGE * 2;
  const candidates = [];
  if (rightGutter >= MIN_GUTTER) candidates.push({ left: union.right + EDGE, top: clampTop(home.top), width: Math.min(width, rightGutter) });
  if (leftGutter >= MIN_GUTTER) {
    const gutterWidth = Math.min(width, leftGutter);
    candidates.push({ left: union.left - EDGE - gutterWidth, top: clampTop(home.top), width: gutterWidth });
  }
  candidates.push({ left: (vw - width) / 2, top: union.top - EDGE / 2 - height, width });
  candidates.push({ left: (vw - width) / 2, top: union.bottom + EDGE / 2, width });
  const fit = candidates.find((p) => p.top >= EDGE / 2 && p.top + height <= vh - EDGE / 2 && clear(p));
  // With no free space the stack stays put; the dialog is layered above it, never the reverse.
  return { ...home, ...(fit || {}), dialog: true };
}
