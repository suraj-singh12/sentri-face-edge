import { useEffect, useState } from "react";

export function usePersistentState(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initialValue : JSON.parse(stored);
    } catch (error) {
      console.debug("[sentriface-ui] saved state unavailable", key, error);
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.debug("[sentriface-ui] unable to save state", key, error);
    }
  }, [key, value]);

  return [value, setValue];
}
