import { useCallback, useEffect, useState } from "react";
import { Coordinates, loadMapCatalogue } from "./map-domain";
import { Landmark, Story } from "./story-domain";

export function useStoryCatalogue(coordinates: Coordinates | null) {
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [loadedCoordinateKey, setLoadedCoordinateKey] = useState("");
  const coordinateKey = coordinates ? `${coordinates.latitude},${coordinates.longitude}` : "all";

  const reload = useCallback(() => setRetry((current) => current + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    loadMapCatalogue(undefined, coordinates)
      .then((catalogue) => {
        if (cancelled) return;
        setLandmarks(catalogue.landmarks);
        setStories(catalogue.stories);
        setLoadedCoordinateKey(coordinateKey);
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [coordinates?.latitude, coordinates?.longitude, coordinateKey, retry]);

  return { landmarks, stories, loading, error, loadedCoordinateKey, reload };
}
