import { Suspense } from "react";
import ContributorWorkspace from "../components/ContributorWorkspace";

export default function PortalPage() {
  return (
    <Suspense fallback={<main className="account-page"><p>Opening your workspace…</p></main>}>
      <ContributorWorkspace />
    </Suspense>
  );
}
