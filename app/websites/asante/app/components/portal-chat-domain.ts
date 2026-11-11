export type PortalChatSelection = { projectId: string | null; publishedId: string | null };

export function portalChatHref(selection: PortalChatSelection): string {
  const params = new URLSearchParams();
  if (selection.projectId) params.set("project", selection.projectId);
  if (selection.publishedId) params.set("published", selection.publishedId);
  const query = params.toString();
  return query ? `/portal/?${query}` : "/portal/";
}

export function readPortalChatSelection(params: URLSearchParams): PortalChatSelection {
  const projectId = params.get("project");
  const publishedId = params.get("published");
  return projectId ? { projectId, publishedId: null } : { projectId: null, publishedId };
}

export function illustrativePublishedHistory(title: string): string[] {
  return [
    `You shared “${title}” with the Asante story archive.`,
    "A contributor prepared the story details and recording for review.",
    "A human reviewer approved the story for the public map.",
  ];
}
