import { notFound } from "next/navigation";
import ControlSurfaceApp from "../control-surface";

const listRoutes = new Set([
  "overview",
  "failure-clusters",
  "datasets",
  "regressions",
  "slos",
  "changes",
]);
const detailRoutes = new Set(["traces", "sessions", "incidents", "releases"]);

export default async function ApplicationRoute({
  params,
}: {
  params: Promise<{ route: string[] }>;
}) {
  const { route } = await params;
  const validList = route.length === 1 && listRoutes.has(route[0]);
  const validDetail =
    (route.length === 1 || route.length === 2) && detailRoutes.has(route[0]);
  const validSettings =
    route.length === 2 && route[0] === "settings" && route[1] === "api-keys";
  if (!validList && !validDetail && !validSettings) notFound();
  return <ControlSurfaceApp />;
}
