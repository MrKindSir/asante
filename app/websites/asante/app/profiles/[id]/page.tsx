"use client";

import { useEffect, useState } from "react";
import { api, languageNames, Story } from "../../components/story-domain";
import StoryPlayer from "../../components/StoryPlayer";

type PublicProfile = { id: string; name: string; language: string; stories: Story[] };

export default function ContributorProfilePage({ params }: { params: { id: string } }) {
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    api<PublicProfile>("/v1/profiles/" + encodeURIComponent(params.id)).then((saved) => { if (active) setProfile(saved); }).catch((cause: Error) => { if (active) setMessage(cause.message); });
    return () => { active = false; };
  }, [params.id]);
  return <main className="account-page"><a className="brand" href="/asante/"><span className="brand-mark">a</span>asante</a><p className="eyebrow">Contributor profile</p><h1>{profile?.name || "Contributor"}</h1>{profile && <><p>Original language: {languageNames[profile.language] || profile.language}</p><h2>Published stories</h2><div className="project-grid">{profile.stories.map((story) => <article className="surface" key={story.id}><h3>{story.title}</h3><p>{story.landmark} · {languageNames[story.language]} · {story.media_format}</p><StoryPlayer story={story} lowData /></article>)}</div>{!profile.stories.length && <p>No published stories yet.</p>}</>}<p role="status">{message || (!profile ? "Loading contributor…" : "")}</p><a href="/asante/">← Explore the map</a></main>;
}
