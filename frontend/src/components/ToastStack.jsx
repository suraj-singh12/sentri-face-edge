import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { ActionIcon, Tooltip } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { IconArrowBackUp } from "@tabler/icons-react";

import { EDGE, TOAST_Z_INDEX, clamp, placeToastStack, readSavedToastPosition, saveToastPosition, toastPositionFromRect } from "../utils/toastPlacement.js";

const DRAG_THRESHOLD = 4;
const STACK_SELECTOR = ".sentriface-toast-stack[data-position='top-right']";

const ToastPositionContext = createContext({ moved: false, reset: () => {} });

function samePlacement(a, b) {
  return Boolean(a) && ["left", "top", "width", "narrow", "dialog"].every((key) => a[key] === b[key]);
}

// Modals and drawers both count as open dialogs. With exactly one open, toasts
// sit above its dimmed backdrop (see CSS); with nested layers Mantine's own
// stacking is kept so an outside click still reaches the top layer.
function openDialogRects() {
  const rects = [...document.querySelectorAll(".mantine-Modal-content, .mantine-Drawer-content")]
    .map((node) => node.getBoundingClientRect())
    .filter((rect) => rect.width > 0 && rect.height > 0);
  document.documentElement.dataset.toastLayers = String(rects.length);
  return rects;
}

function stackHeight() {
  return document.querySelector(STACK_SELECTOR)?.getBoundingClientRect().height || 0;
}

export function ToastContent({ children }) {
  const { moved, reset } = useContext(ToastPositionContext);
  if (!moved) return children;
  return (
    <>
      {children}
      <Tooltip label="Move messages back to the top right" withinPortal openDelay={300}>
        <ActionIcon
          variant="subtle"
          color="gray"
          size={28}
          className="sentriface-toast-reset"
          aria-label="Move messages back to the top right"
          onClick={reset}
        >
          <IconArrowBackUp size={16} aria-hidden="true" />
        </ActionIcon>
      </Tooltip>
    </>
  );
}

export function ToastStack() {
  const [saved, setSaved] = useState(() => (typeof window === "undefined" ? null : readSavedToastPosition()));
  const [placement, setPlacement] = useState(null);
  const [drag, setDrag] = useState(null);
  const frame = useRef(0);
  const dragRef = useRef(null);
  const placementRef = useRef(null);
  useEffect(() => {
    placementRef.current = placement;
  }, [placement]);

  const measure = useCallback(() => {
    window.cancelAnimationFrame(frame.current);
    frame.current = window.requestAnimationFrame(() => {
      const next = placeToastStack({
        viewport: { width: window.innerWidth, height: window.innerHeight },
        saved,
        stackHeight: stackHeight(),
        dialogs: openDialogRects(),
      });
      setPlacement((previous) => (samePlacement(previous, next) ? previous : next));
    });
  }, [saved]);

  useEffect(() => {
    measure();
    const observer = new MutationObserver(measure);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["style"] });
    document.addEventListener("transitionend", measure);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      document.removeEventListener("transitionend", measure);
      window.cancelAnimationFrame(frame.current);
    };
  }, [measure]);

  const reset = useCallback(() => {
    saveToastPosition(null);
    setSaved(null);
  }, []);

  useEffect(() => {
    const onPointerDown = (event) => {
      const current = placementRef.current;
      const toast = event.target.closest?.(`${STACK_SELECTOR} .mantine-Notification-root`);
      if (!toast || event.button !== 0 || !current || current.dialog || event.target.closest("button, a, input, textarea, select")) return;
      dragRef.current = { startX: event.clientX, startY: event.clientY, left: current.left, top: current.top, width: current.width, narrow: current.narrow, active: false };
    };
    const onPointerMove = (event) => {
      const state = dragRef.current;
      if (!state) return;
      const dx = state.narrow ? 0 : event.clientX - state.startX;
      const dy = event.clientY - state.startY;
      if (!state.active && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      if (!state.active) window.getSelection?.()?.removeAllRanges();
      state.active = true;
      event.preventDefault();
      const height = stackHeight();
      state.currentLeft = clamp(state.left + dx, EDGE, window.innerWidth - EDGE - state.width);
      state.currentTop = clamp(state.top + dy, EDGE / 2, window.innerHeight - EDGE / 2 - height);
      setDrag({ left: state.currentLeft, top: state.currentTop });
    };
    const onPointerUp = () => {
      const state = dragRef.current;
      dragRef.current = null;
      if (!state?.active) return;
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const next = toastPositionFromRect({ left: state.currentLeft, top: state.currentTop, width: state.width, height: stackHeight() }, viewport);
      if (state.narrow && saved) next.x = saved.x;
      else if (state.narrow) next.x = 1;
      saveToastPosition(next);
      setPlacement((previous) => ({ ...previous, left: state.currentLeft, top: state.currentTop }));
      setSaved(next);
      setDrag(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointercancel", onPointerUp);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointercancel", onPointerUp);
    };
  }, [saved]);

  const current = placement && drag ? { ...placement, ...drag } : placement;
  const context = { moved: Boolean(saved) && !placement?.dialog, reset };
  return (
    <ToastPositionContext.Provider value={context}>
      <Notifications
        position="top-right"
        zIndex={TOAST_Z_INDEX}
        allowDragDismiss={false}
        className="sentriface-toast-stack"
        data-dragging={drag ? "true" : undefined}
        style={current ? { top: current.top, left: current.left, right: "auto", width: current.width, maxWidth: current.width } : undefined}
      />
    </ToastPositionContext.Provider>
  );
}
