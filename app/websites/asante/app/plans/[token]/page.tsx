import SharedPlan from "./shared-plan";

export default function SharedPlanPage({ params }: { params: { token: string } }) {
  return <SharedPlan token={params.token} />;
}
