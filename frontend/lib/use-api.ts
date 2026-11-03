"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [tick, setTick] = useState(0);
  const key = JSON.stringify([...deps, tick]);
  const [res, setRes] = useState<{ key: string; data?: T; error?: string }>();
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    let cancelled = false;
    fetcherRef.current().then(
      (data) => !cancelled && setRes({ key, data }),
      (e: Error) => !cancelled && setRes((r) => ({ key, data: r?.data, error: e.message })),
    );
    return () => {
      cancelled = true;
    };
  }, [key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const loading = res?.key !== key;
  return { data: res?.data, error: loading ? undefined : res?.error, loading, reload };
}
