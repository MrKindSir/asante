import { useCallback, useEffect, useState } from "react";
import { Coordinates, loadMapCatalogue } from "./map-domain";
import { Landmark, Story } from "./story-domain";

function shuffledStories(stories: Story[]): Story[] {
  const shuffled = [...stories];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

export function useStoryCatalogue(coordinates: Coordinates | null) {
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [loadedCoordinateKey, setLoadedCoordinateKey] = useState("");
  const coordinateKey = coordinates ? `${coordinates.latitude},${coordinates.longitude}` : "all";

  const reload = useCallback(() => setRetry((current) => current + 1), []);
  const shuffle = useCallback(() => setStories((current) => shuffledStories(current)), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    loadMapCatalogue(undefined, coordinates)
      .then((catalogue) => {
        if (cancelled) return;
        setLandmarks(catalogue.landmarks);
        setStories(shuffledStories(catalogue.stories));
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

  return { landmarks, stories, loading, error, loadedCoordinateKey, reload, shuffle };
}
