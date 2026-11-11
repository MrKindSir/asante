export function isDirectAsanteRoute(currentHref: string, directPort: string): boolean {
  const url = new URL(currentHref);
  return url.port === directPort && directPort !== "80";
}

export function alternateAsanteRoute(currentHref: string, directPort: string): string {
  const url = new URL(currentHref);
  url.port = isDirectAsanteRoute(currentHref, directPort) || directPort === "80" ? "" : directPort;
  return url.toString();
}
