import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> { data: T | undefined; error: Error | undefined; loading: boolean; reload: () => void }

/** Runs an async loader whenever `deps` change; stale responses are ignored. `reload` re-runs it (authoritative reread). */
export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stable = useCallback(loader, deps);
  useEffect(() => {
    const my = ++seq.current;
    setLoading(true);
    stable().then(
      (v) => { if (seq.current === my) { setData(v); setError(undefined); setLoading(false); } },
      (e: unknown) => { if (seq.current === my) { setError(e instanceof Error ? e : new Error(String(e))); setLoading(false); } },
    );
  }, [stable, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
