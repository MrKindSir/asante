import { RefObject, useCallback, useEffect, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { accuracyFeatures, Coordinates, landmarkFeatures } from "./map-domain";
import { Landmark, Story } from "./story-domain";

export const AFRICA_MAP_CENTER: [number, number] = [20, 2];
export const AFRICA_MAP_ZOOM = 2.35;

type MapOptions = {
  canvas: RefObject<HTMLDivElement>;
  landmarks: Landmark[];
  coordinates: Coordinates | null;
  onLandmarkSelect: (landmarkId: string) => void;
};

export function useLandmarkMap({ canvas, landmarks, coordinates, onLandmarkSelect }: MapOptions) {
  const map = useRef<MapLibreMap | null>(null);
  const selectRef = useRef(onLandmarkSelect);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { selectRef.current = onLandmarkSelect; }, [onLandmarkSelect]);

  useEffect(() => {
    let disposed = false;
    let instance: MapLibreMap | undefined;
    let observer: ResizeObserver | undefined;
    setReady(false);
    setError("");

    import("maplibre-gl").then(({ default: maplibregl }) => {
      if (disposed || !canvas.current) return;
      try {
        instance = new maplibregl.Map({
          container: canvas.current,
          style: {
            version: 8,
            sources: {
              streets: {
                type: "raster",
                tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                tileSize: 256,
                maxzoom: 19,
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
              },
            },
            layers: [{ id: "streets", type: "raster", source: "streets" }],
          },
          center: AFRICA_MAP_CENTER,
          zoom: AFRICA_MAP_ZOOM,
          attributionControl: { compact: false },
        });
        map.current = instance;
        instance.addControl(new maplibregl.NavigationControl(), "bottom-right");
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(canvas.current);
        instance.on("error", () => setError("Some map tiles could not load. Retry the map or browse the story list."));
        instance.on("load", () => {
          if (disposed || !instance) return;
          instance.resize();
          const palette = getComputedStyle(document.documentElement);
          const color = (token: string) => palette.getPropertyValue(token).trim();
          instance.addSource("asante-landmarks", {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
            cluster: true,
            clusterRadius: 45,
          });
          instance.addLayer({
            id: "asante-clusters",
            type: "circle",
            source: "asante-landmarks",
            filter: ["has", "point_count"],
            paint: {
              "circle-color": color("--green"),
              "circle-radius": 23,
              "circle-stroke-color": color("--paper"),
              "circle-stroke-width": 3,
            },
          });
          instance.addLayer({
            id: "asante-pins",
            type: "circle",
            source: "asante-landmarks",
            filter: ["!", ["has", "point_count"]],
            paint: {
              "circle-color": color("--clay"),
              "circle-radius": 11,
              "circle-stroke-width": 4,
              "circle-stroke-color": color("--paper"),
            },
          });
          instance.on("click", "asante-pins", (event) => {
            const id = String(event.features?.[0]?.properties?.id || "");
            if (id) selectRef.current(id);
          });
          instance.on("click", "asante-clusters", async (event) => {
            const feature = event.features?.[0];
            if (!feature || feature.geometry.type !== "Point" || !instance) return;
            const source = instance.getSource("asante-landmarks") as GeoJSONSource;
            const zoom = await source.getClusterExpansionZoom(Number(feature.properties?.cluster_id));
            if (!disposed) instance.easeTo({ center: feature.geometry.coordinates as [number, number], zoom });
          });
          setReady(true);
        });
      } catch {
        setError("The map could not start. Check that WebGL is enabled, or use the story list.");
      }
    }).catch(() => setError("The map could not load. Retry or browse the story list."));

    return () => {
      disposed = true;
      observer?.disconnect();
      instance?.remove();
      map.current = null;
    };
  }, [canvas, attempt]);

  useEffect(() => {
    const source = map.current?.getSource("asante-landmarks") as GeoJSONSource | undefined;
    source?.setData(landmarkFeatures(landmarks));
  }, [landmarks, ready]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !coordinates) return;
    const data = accuracyFeatures(coordinates);
    const source = instance.getSource("asante-accuracy") as GeoJSONSource | undefined;
    if (source) source.setData(data);
    else {
      instance.addSource("asante-accuracy", { type: "geojson", data });
      instance.addLayer({
        id: "asante-accuracy",
        type: "fill",
        source: "asante-accuracy",
        paint: {
          "fill-color": getComputedStyle(document.documentElement).getPropertyValue("--blue").trim(),
          "fill-opacity": 0.2,
        },
      });
    }
  }, [coordinates, ready]);

  const focusCoordinates = useCallback((next: Pick<Coordinates, "latitude" | "longitude">) => {
    map.current?.easeTo({ center: [next.longitude, next.latitude], zoom: 11 });
  }, []);

  const focusStory = useCallback((story: Story, places: Landmark[]) => {
    const place = places.find((landmark) => landmark.id === story.landmark_id);
    if (place) {
      map.current?.easeTo({
        center: [place.longitude, place.latitude],
        zoom: 13,
        padding: {
          left: window.innerWidth > 1100 ? 450 : 0,
          right: window.innerWidth > 1100 ? 370 : 0,
          top: 100,
          bottom: 50,
        },
      });
    }
  }, []);

  const showAll = useCallback(() => {
    map.current?.easeTo({ center: AFRICA_MAP_CENTER, zoom: AFRICA_MAP_ZOOM, padding: 0 });
  }, []);

  const retryMap = useCallback(() => setAttempt((current) => current + 1), []);

  return { ready, error, focusCoordinates, focusStory, showAll, retryMap };
}
