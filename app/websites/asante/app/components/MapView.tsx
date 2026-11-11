"use client";

import { useEffect, useRef, useState } from "react";
import { guideSteps, languageNames, readGuide, Story } from "./story-domain";
import { Coordinates } from "./map-domain";
import { useLandmarkMap } from "./useLandmarkMap";
import { useMapDiscovery } from "./useMapDiscovery";
import { useStoryCatalogue } from "./useStoryCatalogue";
import GuidedTour from "./GuidedTour";
import StoryPlayer from "./StoryPlayer";
import StoryArtPreview, { canPreviewStoryVideo } from "./StoryArtPreview";
import { openWorkspace, savePreference } from "./workspace-client";

const guideKey = "asante.onboarding.v2";
const liveLocationKey = "asante.liveLocation";

export default function MapView() {
  const canvas = useRef<HTMLDivElement>(null);
  const storyListRef = useRef<HTMLDivElement>(null);
  const locationWatchId = useRef<number | null>(null);
  const focusedLiveLocation = useRef(false);
  const liveLocationRef = useRef(false);
  const [step, setStep] = useState<number | null>(null);
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);
  const [location, setLocation] = useState("");
  const [lowData, setLowData] = useState(false);
  const [liveLocation, setLiveLocation] = useState(false);
  const [prefsReady, setPrefsReady] = useState(false);
  const [listOpen, setListOpen] = useState(true);
  const [hoverPreviewId, setHoverPreviewId] = useState<string | null>(null);
  const [scrollPreviewId, setScrollPreviewId] = useState<string | null>(null);
  const lastWatchedCoordinates = useRef<Coordinates | null>(null);
  const catalogue = useStoryCatalogue(coordinates);
  const discovery = useMapDiscovery(catalogue.stories);
  const map = useLandmarkMap({
    canvas,
    landmarks: catalogue.landmarks,
    coordinates,
    onLandmarkSelect: (landmarkId) => {
      discovery.selectLandmark(landmarkId);
      setListOpen(true);
    },
  });
  const previewStoryId = hoverPreviewId || scrollPreviewId;

  function clearLocationWatch() {
    if (locationWatchId.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(locationWatchId.current);
      locationWatchId.current = null;
    }
  }

  function setLiveLocationEnabled(enabled: boolean) {
    liveLocationRef.current = enabled;
    setLiveLocation(enabled);
  }

  function locate() {
    if (!navigator.geolocation) {
      setLocation("Location unavailable · every story is still accessible");
      return;
    }
    setLocation("Waiting for location permission…");
    clearLocationWatch();
    focusedLiveLocation.current = false;
    locationWatchId.current = navigator.geolocation.watchPosition(
      ({ coords }) => {
        const next = { latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy };
        const previous = lastWatchedCoordinates.current;
        const movedFar = !previous || (() => {
          const latitudeDelta = (next.latitude - previous.latitude) * 111_320;
          const longitudeDelta = (next.longitude - previous.longitude) * 111_320 * Math.cos(previous.latitude * Math.PI / 180);
          return Math.hypot(latitudeDelta, longitudeDelta) >= 30;
        })();
        setLiveLocationEnabled(true);
        setLocation("");
        void savePreference(liveLocationKey, "true").catch(() => undefined);
        if (!focusedLiveLocation.current) {
          focusedLiveLocation.current = true;
          lastWatchedCoordinates.current = next;
          setCoordinates(next);
          map.focusCoordinates(next);
          return;
        }
        if (!movedFar) return;
        lastWatchedCoordinates.current = next;
        setCoordinates(next);
      },
      () => {
        setLiveLocationEnabled(false);
        setCoordinates(null);
        lastWatchedCoordinates.current = null;
        setLocation("Location was not shared · explore every story with search or the map");
        clearLocationWatch();
        void savePreference(liveLocationKey, "false").catch(() => undefined);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 15000 },
    );
  }

  useEffect(() => {
    let active = true;
    openWorkspace().then((saved) => {
      if (!active) return;
      setStep(readGuide(saved.preferences[guideKey] || null));
      setLowData(saved.preferences["asante.lowData"] === "true");
      const enabled = saved.preferences[liveLocationKey] === "true";
      liveLocationRef.current = enabled;
      setLiveLocation(enabled);
      setPrefsReady(true);
      if (enabled) locate();
    }).catch(() => {
      if (!active) return;
      setStep(0);
      setPrefsReady(true);
    });
    return () => {
      active = false;
      clearLocationWatch();
    };
    // Initial preference hydrate only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!prefsReady || liveLocationRef.current) return;
    const timer = window.setTimeout(() => {
      if (!liveLocationRef.current) locate();
    }, 15000);
    return () => window.clearTimeout(timer);
    // Ask once after prefs load while live location is still off.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefsReady]);

  useEffect(() => {
    if (lowData) {
      setScrollPreviewId(null);
      setHoverPreviewId(null);
      return;
    }
    const root = storyListRef.current;
    if (!root || !listOpen) {
      setScrollPreviewId(null);
      return;
    }
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setScrollPreviewId(null);
      return;
    }
    const ratios = new Map<string, number>();
    const pickBest = () => {
      let bestId: string | null = null;
      let bestRatio = 0.45;
      for (const [id, ratio] of ratios) {
        if (ratio >= bestRatio) {
          bestRatio = ratio;
          bestId = id;
        }
      }
      setScrollPreviewId(bestId);
    };
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = (entry.target as HTMLElement).dataset.storyId;
        if (!id) continue;
        ratios.set(id, entry.isIntersecting ? entry.intersectionRatio : 0);
      }
      pickBest();
    }, { root, threshold: [0.35, 0.5, 0.65, 0.8, 1] });
    const cards = root.querySelectorAll<HTMLElement>("[data-story-id][data-preview-video='true']");
    cards.forEach((card) => observer.observe(card));
    pickBest();
    return () => {
      observer.disconnect();
      ratios.clear();
    };
  }, [listOpen, lowData, discovery.visible]);

  function moveGuide(next: number) {
    setListOpen(true);
    setStep(next >= guideSteps.length ? null : next);
    void savePreference(guideKey, JSON.stringify({ version: 2, step: Math.min(5, next) })).catch(() => undefined);
  }

  function openStory(story: Story) {
    setHoverPreviewId(null);
    discovery.selectStory(story);
    map.focusStory(story, catalogue.landmarks);
  }
  const selected = discovery.selected;

  return <main className="map-app">
    <div className="map-canvas" ref={canvas} aria-label="Landmark map" />
    <header className="map-header">
      <a className="brand" href="/asante/"><span className="brand-mark">a</span>asante<span className="brand-caption">stories live here</span></a>
      <nav className="map-nav" aria-label="Map actions">
        <label className="tool-chip nav-tool-chip" title={lowData ? "Low data on: media waits for Play and list previews stay still" : "Low data off: muted list previews play as you scroll"}>
          <input
            type="checkbox"
            checked={lowData}
            onChange={(event) => {
              const next = event.target.checked;
              setLowData(next);
              if (next) {
                setHoverPreviewId(null);
                setScrollPreviewId(null);
              }
              void savePreference("asante.lowData", String(next)).catch(() => undefined);
            }}
          />
          <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7.5h16v2H4zm2 4h12v2H6zm2 4h8v2H8z" fill="currentColor"/></svg>
          Low data
        </label>
        {!liveLocation && (
          <button type="button" className="button nav-action nav-location" data-tour="location" onClick={locate}>
            <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a7 7 0 0 1 7 7c0 4.4-5.1 9.7-6.4 11a.9.9 0 0 1-1.2 0C10.1 19.7 5 14.4 5 10a7 7 0 0 1 7-7Zm0 4.5A2.5 2.5 0 1 0 12 12a2.5 2.5 0 0 0 0-5Z" fill="currentColor"/></svg>
            Allow Live Location
          </button>
        )}
        <a className="button nav-action nav-login" data-tour="contribute" href="/asante/portal/">
          <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0 9.5c3.6 0 6.5 2.1 6.5 4.7v1.3H5.5v-1.3C5.5 15.1 8.4 13 12 13Z" fill="currentColor"/></svg>
          Login
        </a>
      </nav>
    </header>
    <section className={"discovery-panel " + (listOpen ? "" : "collapsed")} aria-label="Discover stories">
      <div className="panel-heading"><div><p className="eyebrow">Listen to a place</p><h1>Explore every story.</h1></div><button type="button" className="icon-button" onClick={() => { if (!listOpen) catalogue.shuffle(); setListOpen(!listOpen); }} aria-label={listOpen ? "Hide story list" : "Show story list"}>{listOpen ? <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 11h12v2H6z" fill="currentColor"/></svg> : <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 6h2v5h5v2h-5v5h-2v-5H6v-2h5z" fill="currentColor"/></svg>}</button></div>
      {listOpen && <>
        <label className="search" data-tour="search"><span>⌕</span><input aria-label="Search stories and landmarks" placeholder="A place, a voice, a story…" value={discovery.query} onChange={(event) => discovery.dispatch({ type: "query-changed", query: event.target.value })} /></label>
        <div className="filter-row"><select aria-label="Story language" value={discovery.language} onChange={(event) => discovery.dispatch({ type: "language-changed", language: event.target.value })}><option value="">All languages</option>{Object.entries(languageNames).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select><span className="muted">Listen from anywhere</span></div>
        <div className="discovery-meta"><span>{catalogue.loading ? "Finding stories…" : discovery.visible.length + " stories to explore"}</span><div><button className="quiet" onClick={catalogue.shuffle} disabled={catalogue.loading || discovery.visible.length < 2}>Shuffle</button><button className="quiet" onClick={catalogue.reload} disabled={catalogue.loading}>Refresh</button><button className="quiet" onClick={() => { discovery.showAll(); map.showAll(); }}>Show all</button></div></div>
        <div className="story-list" data-tour="story-list" ref={storyListRef}>
          {catalogue.error && <div className="notice" role="alert">{catalogue.error}<button onClick={catalogue.reload}>Try again</button></div>}
          {!catalogue.loading && !catalogue.error && discovery.visible.length === 0 && <p>No stories match these filters. Choose Show all to explore other places.</p>}
          {discovery.visible.map((story, index) => {
            const canPreview = canPreviewStoryVideo(story);
            const previewing = !lowData && previewStoryId === story.id;
            return <button
              key={story.id}
              type="button"
              data-tour={index === 0 ? "story" : undefined}
              data-story-id={story.id}
              data-preview-video={canPreview ? "true" : undefined}
              className={"story-card " + (discovery.selected?.id === story.id ? "selected" : "") + (previewing ? " nearby-preview" : "")}
              onClick={() => openStory(story)}
              onMouseEnter={() => { if (!lowData && canPreview) setHoverPreviewId(story.id); }}
              onMouseLeave={() => setHoverPreviewId((current) => current === story.id ? null : current)}
            >
              <StoryArtPreview story={story} artClass={"art-" + index % 3} playing={previewing}/>
              <span className="story-copy"><small>{story.landmark}{story.distance_m !== null ? " · " + (story.distance_m / 1000).toFixed(1) + " km away" : ""}</small><strong>{story.title}</strong><span>By {story.contributor_name}</span><span className="story-tags">{languageNames[story.language]} · {story.media_format} · {story.media_url ? "playable" : "media pending"}</span></span><span className="story-arrow">↗</span>
            </button>;
          })}
        </div>
        <div className="panel-footer" role="status">
          {coordinates
            ? <>{coordinates.latitude.toFixed(5)}, {coordinates.longitude.toFixed(5)} · accuracy ±{Math.round(coordinates.accuracy)} m</>
            : (location || "Live location off · stories stay available everywhere")}
          <small>Audio demo available · other story records are illustrative</small>
        </div>
      </>}
    </section>
    {map.error && <div className="map-status" role="status">{map.error}<button className="quiet" onClick={map.retryMap}>Retry map</button></div>}
    {selected && <aside className="story-drawer" aria-label="Selected story">
      <button className="close" aria-label="Close story" onClick={discovery.closeStory}>×</button>
      <p className="eyebrow">{selected.landmark}</p><h2>{selected.title}</h2>
      <p>Contributed by <strong>{selected.contributor_name}</strong></p>
      <div className="tag-row"><span>{languageNames[selected.language]}</span><span>{selected.media_format}</span><span>{selected.is_demo ? "Playback demo" : "Illustrative record"}</span></div>
      <StoryPlayer key={selected.id} story={selected} lowData={lowData} />
      <h3>Story location</h3><p>{selected.landmark} · {selected.region}</p>
      <p className="muted">{selected.latitude}, {selected.longitude} · available to listeners everywhere</p>
      <h3>Language & access</h3>
      <p>{languageNames[selected.language] || selected.language} · listed story language. Play the recording to choose available caption languages.</p>
      <details><summary>Credit, evidence & ownership</summary><p>Attribution: {selected.contributor_name}. {selected.is_demo ? "An original synthetic recording made to test the Asante listening experience." : "An illustrative record awaiting its original media and source packet."}</p></details>
    </aside>}
    {step !== null && <GuidedTour key={step + ":" + (catalogue.loading ? "loading" : "ready")} step={step} onMove={moveGuide} onLocate={locate} onOpenStory={() => { if (discovery.visible[0]) openStory(discovery.visible[0]); }} />}
  </main>;
}
