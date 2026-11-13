import { Suspense } from "react";
import ContributorWorkspace from "../components/ContributorWorkspace";

export default function ReviewPage() {
  return (
    <Suspense fallback={<main className="account-page"><p>Opening the review desk…</p></main>}>
      <ContributorWorkspace />
    </Suspense>
  );
}
