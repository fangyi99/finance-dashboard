import { useEffect, useState } from "react";

// Fetches one widget's data. Each widget calls this on its own, so a failure in one never
// blocks the others. `refreshKey` is bumped by the dashboard (on focus, on pull-to-refresh)
// to make every widget fetch again.
export function useWidgetData<T>(url: string, refreshKey: number) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    fetch(url)
      .then((res) => {
        if (!res.ok)
          throw new Error(`Couldn't load this widget (${res.status})`);
        return res.json();
      })
      .then((json) => {
        if (active) setData(json);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [url, refreshKey]);

  return { data, loading, error };
}
