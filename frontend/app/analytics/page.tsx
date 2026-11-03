"use client";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/form";
import { ClassificationBadge } from "@/components/classification";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { fmtScore } from "@/lib/utils";

const COLORS: Record<string, string> = { HOT: "var(--hot)", WARM: "var(--warm)", COLD: "var(--cold)" };
const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink)" };

export default function AnalyticsPage() {
  const { data: o, error, reload } = useApi(() => api.overview());
  if (error) return <><PageHeader title="Analytics" /><ErrorState message={error} onRetry={reload} /></>;
  if (!o) return <><PageHeader title="Analytics" /><Skeleton className="h-96" /></>;
  if (o.assessed_leads === 0)
    return <><PageHeader title="Analytics" /><EmptyState title="Nothing to analyse yet" body="Charts appear once at least one lead has been assessed." href="/leads/new" cta="Add lead" /></>;

  const pie = o.classification_distribution.filter((d) => d.value > 0);
  return (
    <>
      <PageHeader title="Analytics" subtitle={`Based on the latest assessment of ${o.assessed_leads} lead${o.assessed_leads > 1 ? "s" : ""}. Average score ${fmtScore(o.average_score)}.`} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Lead classification distribution</CardTitle></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={62} outerRadius={100} paddingAngle={2} stroke="var(--surface)"
                  label={({ name, value }) => `${name} ${value}`}>
                  {pie.map((d) => <Cell key={d.name} fill={COLORS[d.name]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Lead score distribution</CardTitle></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={o.score_distribution} margin={{ left: -16 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="range" tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
                <YAxis allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--soft)" }} />
                <Bar dataKey="count" name="Leads" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
      <Card className="mt-5 overflow-hidden">
        <CardHeader><CardTitle>Lead category statistics</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead className="text-muted"><tr>{["Category", "Leads", "Share", "Average", "Lowest", "Highest"].map((h) => <th key={h} className="py-2 pr-4 font-semibold">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {o.category_statistics.map((s) => (
                <tr key={s.classification}>
                  <td className="py-3 pr-4"><ClassificationBadge value={s.classification} /></td>
                  <td className="num py-3 pr-4 font-semibold">{s.count}</td>
                  <td className="num py-3 pr-4">{s.percentage}%</td>
                  <td className="num py-3 pr-4">{fmtScore(s.average_score)}</td>
                  <td className="num py-3 pr-4">{fmtScore(s.min_score)}</td>
                  <td className="num py-3 pr-4">{fmtScore(s.max_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-sm text-muted">
            Data confidence: {o.confidence_distribution.map((c) => `${c.value} ${c.name.toLowerCase()}`).join(", ")}.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
