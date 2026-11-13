import { Dispatch, useMemo, useReducer } from "react";
import { DiscoveryAction, discoveryReducer, initialDiscoveryState, visibleStories } from "./map-domain";
import { Story } from "./story-domain";

export function useMapDiscovery(stories: Story[]) {
  const [state, dispatch] = useReducer(discoveryReducer, initialDiscoveryState);
  const visible = useMemo(() => visibleStories(stories, state), [stories, state]);
  const selected = stories.find((story) => story.id === state.selectedStoryId) || null;

  function selectLandmark(landmarkId: string) {
    const story = stories.find((candidate) => candidate.landmark_id === landmarkId);
    dispatch({ type: "landmark-selected", landmarkId, storyId: story?.id || null });
  }

  function selectStory(story: Story) {
    dispatch({ type: "story-selected", storyId: story.id });
  }

  function closeStory() {
    dispatch({ type: "story-closed" });
  }

  function showAll() {
    dispatch({ type: "show-all" });
  }

  return {
    query: state.query,
    landmarkId: state.landmarkId,
    language: state.language,
    selected,
    visible,
    dispatch: dispatch as Dispatch<DiscoveryAction>,
    selectLandmark,
    selectStory,
    closeStory,
    showAll,
  };
}
