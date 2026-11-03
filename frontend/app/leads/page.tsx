"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input, Skeleton } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { ClassificationBadge, ConfidenceBadge } from "@/components/classification";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn, fmtScore, formatDate } from "@/lib/utils";

const FILTERS = [["", "All"], ["HOT", "Hot"], ["WARM", "Warm"], ["COLD", "Cold"], ["UNASSESSED", "Not assessed"]];
const PAGE = 15;

function Leads() {
  const router = useRouter();
  const sp = useSearchParams();
  const cls = sp.get("classification") ?? "";
  const [text, setText] = useState(sp.get("search") ?? "");
  const [search, setSearch] = useState(text);
  const [page, setPage] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => { setSearch(text.trim()); setPage(0); }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const { data, error, loading, reload } = useApi(
    () => api.leads({ search, classification: cls, limit: PAGE, offset: page * PAGE }), [search, cls, page]);

  const setFilter = (v: string) => { setPage(0); router.replace(v ? `/leads?classification=${v}` : "/leads"); };

  return (
    <>
      <PageHeader title="Leads" subtitle="Search, filter and open any lead's assessment."
        actions={<Button asChild><Link href="/leads/new">Add lead</Link></Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" aria-hidden />
          <Input aria-label="Search leads" className="pl-9" placeholder="Search name, company, email, industry"
            value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by classification">
          {FILTERS.map(([v, label]) => (
            <button key={v} onClick={() => setFilter(v)} aria-pressed={cls === v}
              className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold cursor-pointer transition-colors",
                cls === v ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-muted hover:text-ink")}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {error ? <ErrorState message={error} onRetry={reload} /> :
        !data ? <Skeleton className="h-72" /> :
        data.items.length === 0 ? (
          search || cls ? <EmptyState title="No leads match" body="Try a different search term or clear the filter." />
            : <EmptyState title="No leads yet" body="Leads you add appear here with their score and classification." href="/leads/new" cta="Add lead" />
        ) : (
          <Card className={cn("overflow-hidden", loading && "opacity-60")}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-line bg-soft/60 text-muted">
                  <tr>{["Lead", "Role", "Score", "Class", "Confidence", "Added"].map((h) => <th key={h} className="px-4 py-2.5 font-semibold">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.items.map((l) => (
                    <tr key={l.id} className="hover:bg-soft/50">
                      <td className="px-4 py-3">
                        <Link href={`/leads/${l.id}`} className="font-semibold text-ink hover:text-accent">{l.name ?? l.company_name}</Link>
                        <div className="text-muted">{l.name ? l.company_name : ""}</div>
                      </td>
                      <td className="px-4 py-3 text-muted">{l.job_title ?? "–"}</td>
                      <td className="num px-4 py-3 font-semibold">{fmtScore(l.latest_assessment?.score)}</td>
                      <td className="px-4 py-3">{l.latest_assessment ? <ClassificationBadge value={l.latest_assessment.classification} /> : <span className="text-muted">Not assessed</span>}</td>
                      <td className="px-4 py-3">{l.latest_assessment ? <ConfidenceBadge value={l.latest_assessment.confidence_level} /> : "–"}</td>
                      <td className="px-4 py-3 text-muted whitespace-nowrap">{formatDate(l.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-muted">
              <span>{data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button variant="outline" size="sm" disabled={data.offset + PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          </Card>
        )}
    </>
  );
}

export default function LeadsPage() {
  return <Suspense fallback={<Skeleton className="h-72" />}><Leads /></Suspense>;
}
