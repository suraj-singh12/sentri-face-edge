import { useEffect, useRef } from "react";

// Call before an action that opens a form. The effect runs after React commits
// the new form; unrelated renders and restored drafts cannot move the viewport.
export function useIntentionalFormScroll(formId) {
  const elementRef = useRef(null);
  const pendingRef = useRef(false);

  const requestScroll = () => { pendingRef.current = true; };

  useEffect(() => {
    if (!formId || !pendingRef.current) return;
    pendingRef.current = false;
    elementRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [formId]);

  return [elementRef, requestScroll];
}
