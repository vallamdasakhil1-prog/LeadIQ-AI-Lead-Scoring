"use client";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { ClassificationBadge } from "@/components/classification";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { fmtScore, formatDate } from "@/lib/utils";

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <Card className="p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`num mt-1 text-3xl font-bold ${tone ?? ""}`}>{value}</p>
    </Card>
  );
}

export default function Dashboard() {
  const overview = useApi(() => api.overview());
  const recent = useApi(() => api.leads({ limit: 6 }));
  const o = overview.data;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live figures from your stored leads and their latest assessments."
        actions={<Button asChild><Link href="/leads/new">Add lead</Link></Button>} />
      {overview.error && <ErrorState message={overview.error} onRetry={overview.reload} />}
      {!overview.error && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          {!o ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[98px]" />) : (
            <>
              <Metric label="Total leads" value={o.total_leads} />
              <Metric label="Hot leads" value={o.hot_leads} tone="text-hot" />
              <Metric label="Warm leads" value={o.warm_leads} tone="text-warm" />
              <Metric label="Cold leads" value={o.cold_leads} tone="text-cold" />
              <Metric label="Average score" value={fmtScore(o.average_score)} />
            </>
          )}
        </div>
      )}
      {o && o.unassessed_leads > 0 && (
        <p className="mt-4 text-sm text-muted">
          {o.unassessed_leads} lead{o.unassessed_leads > 1 ? "s are" : " is"} waiting for an assessment and not counted above.{" "}
          <Link href="/leads?classification=UNASSESSED" className="font-semibold text-accent underline">Review them</Link>
        </p>
      )}
      <Card className="mt-8">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent leads</CardTitle>
          <Link href="/leads" className="text-sm font-semibold text-accent">View all</Link>
        </CardHeader>
        <CardContent>
          {recent.error ? <ErrorState message={recent.error} onRetry={recent.reload} /> :
            !recent.data ? <Skeleton className="h-40" /> :
            recent.data.items.length === 0 ? (
              <EmptyState title="No leads yet" body="Add your first lead to see it scored. The form can pre-fill a sample lead."
                href="/leads/new?sample=1" cta="Add the sample lead" />
            ) : (
              <ul className="divide-y divide-line">
                {recent.data.items.map((l) => (
                  <li key={l.id}>
                    <Link href={`/leads/${l.id}`} className="flex items-center justify-between gap-3 py-3 hover:bg-soft/60 rounded-md px-2 -mx-2">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{l.name ?? l.company_name}</p>
                        <p className="truncate text-sm text-muted">{[l.job_title, l.company_name].filter(Boolean).join(" · ") || "No company details"}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        {l.latest_assessment ? (<>
                          <span className="num text-sm font-semibold">{fmtScore(l.latest_assessment.score)}</span>
                          <ClassificationBadge value={l.latest_assessment.classification} />
                        </>) : <span className="text-xs text-muted">Not assessed · {formatDate(l.created_at)}</span>}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
        </CardContent>
      </Card>
    </>
  );
}
