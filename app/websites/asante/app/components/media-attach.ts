import Hls from "hls.js";

export function isHlsUrl(url: string): boolean {
  return url.includes(".m3u8");
}

export function attachMedia(element: HTMLMediaElement, url: string, onError: () => void): () => void {
  if (element instanceof HTMLVideoElement && isHlsUrl(url) && Hls.isSupported()) {
    const hls = new Hls({ enableWorker: true, lowLatencyMode: false });
    hls.loadSource(url);
    hls.attachMedia(element);
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) onError();
    });
    return () => {
      hls.destroy();
    };
  }
  if (element instanceof HTMLVideoElement && isHlsUrl(url) && element.canPlayType("application/vnd.apple.mpegurl")) {
    element.src = url;
    return () => {
      element.removeAttribute("src");
      element.load();
    };
  }
  element.src = url;
  return () => {
    element.removeAttribute("src");
    element.load();
  };
}
