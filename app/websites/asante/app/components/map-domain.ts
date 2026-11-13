import { api, filterStories, Landmark, Story } from "./story-domain";

export type Coordinates = { latitude: number; longitude: number; accuracy: number };
export type MapCatalogue = { landmarks: Landmark[]; stories: Story[] };
export type CatalogueRequest = <T>(path: string) => Promise<T>;

export async function loadMapCatalogue(
  request: CatalogueRequest = api,
  coordinates: Coordinates | null = null,
): Promise<MapCatalogue> {
  const params = coordinates
    ? "?latitude=" + coordinates.latitude + "&longitude=" + coordinates.longitude
    : "";
  const [places, results] = await Promise.all([
    request<{ items: Landmark[] }>("/v1/landmarks"),
    request<{ items: Story[] }>("/v1/stories" + params),
  ]);
  return { landmarks: places.items, stories: results.items };
}

export type DiscoveryState = {
  query: string;
  landmarkId: string;
  language: string;
  selectedStoryId: string | null;
};

export type DiscoveryAction =
  | { type: "query-changed"; query: string }
  | { type: "language-changed"; language: string }
  | { type: "landmark-selected"; landmarkId: string; storyId: string | null }
  | { type: "story-selected"; storyId: string }
  | { type: "story-closed" }
  | { type: "show-all" };

export const initialDiscoveryState: DiscoveryState = {
  query: "",
  landmarkId: "",
  language: "",
  selectedStoryId: null,
};

export function discoveryReducer(state: DiscoveryState, action: DiscoveryAction): DiscoveryState {
  switch (action.type) {
    case "query-changed":
      return { ...state, query: action.query, landmarkId: "" };
    case "language-changed":
      return { ...state, language: action.language };
    case "landmark-selected":
      return {
        query: "",
        landmarkId: action.landmarkId,
        language: "",
        selectedStoryId: action.storyId,
      };
    case "story-selected":
      return { ...state, selectedStoryId: action.storyId };
    case "story-closed":
      return { ...state, selectedStoryId: null };
    case "show-all":
      return initialDiscoveryState;
  }
}

export function visibleStories(stories: Story[], state: DiscoveryState): Story[] {
  const atLandmark = state.landmarkId
    ? stories.filter((story) => story.landmark_id === state.landmarkId)
    : stories;
  return filterStories(atLandmark, state.query, state.language);
}

export function nearestPlayableStory(stories: Story[], maxDistanceM = 150): Story | null {
  return stories
    .filter((story) => Boolean(story.media_url) && story.distance_m !== null && story.distance_m <= maxDistanceM)
    .sort((left, right) => (left.distance_m ?? Number.POSITIVE_INFINITY) - (right.distance_m ?? Number.POSITIVE_INFINITY))[0] || null;
}

export function landmarkFeatures(landmarks: Landmark[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: landmarks.map((place) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [place.longitude, place.latitude] },
      properties: { id: place.id, name: place.name },
    })),
  };
}

export function accuracyFeatures({ latitude, longitude, accuracy }: Coordinates): GeoJSON.FeatureCollection<GeoJSON.Polygon> {
  const ring = Array.from({ length: 65 }, (_, index) => {
    const angle = index / 64 * Math.PI * 2;
    const longitudeScale = 111320 * Math.max(0.01, Math.cos(latitude * Math.PI / 180));
    return [
      longitude + Math.cos(angle) * accuracy / longitudeScale,
      latitude + Math.sin(angle) * accuracy / 111320,
    ];
  });
  ring[64] = ring[0];
  return {
    type: "FeatureCollection",
    features: [{
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: [ring] },
    }],
  };
}
