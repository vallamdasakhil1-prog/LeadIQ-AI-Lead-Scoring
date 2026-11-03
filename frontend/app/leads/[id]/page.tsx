"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, MinusCircle, RefreshCw, Sparkles, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { ClassificationBadge, ConfidenceBadge, CLASS_COLOR } from "@/components/classification";
import { ScoreDial } from "@/components/score-dial";
import { ErrorState, PageHeader } from "@/components/states";
import { api, type Assessment } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatDate, fmtScore } from "@/lib/utils";

const COMPONENT_LABELS: Record<string, string> = {
  data_completeness: "Data completeness", contact_validity: "Contact format validity (not verified)",
  information_reliability: "Information reliability", consistency: "Consistency",
};

function Factors({ title, items, positive }: { title: string; items: string[]; positive: boolean }) {
  const Icon = positive ? CheckCircle2 : MinusCircle;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        {items.length === 0 ? <p className="text-sm text-muted">None identified.</p> : (
          <ul className="space-y-2">
            {items.map((t) => (
              <li key={t} className="flex gap-2 text-sm">
                <Icon className={`mt-0.5 size-4 shrink-0 ${positive ? "text-pos" : "text-neg"}`} aria-hidden /> {t}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function AssessmentPage() {
  const { id } = useParams<{ id: string }>();
  const lead = useApi(() => api.lead(id), [id]);
  const [version, setVersion] = useState(0);
  const assessment = useApi(() => api.assessment(id), [id, version]);
  const history = useApi(() => api.history(id), [id, version]);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string>();

  async function run() {
    setBusy(true); setRunError(undefined);
    try { await api.assess(id); setVersion((v) => v + 1); }
    catch (e) { setRunError((e as Error).message); }
    finally { setBusy(false); }
  }

  const l = lead.data;
  const a: Assessment | undefined = assessment.data;
  const notAssessed = (assessment.error ?? "").includes("not been assessed");
  const title = l ? (l.name ?? l.company_name ?? `Lead ${id}`) : "Lead assessment";
  const issues = l?.validation_report?.fields.filter((f) => f.status !== "valid") ?? [];
  const warnings = l?.validation_report?.warnings ?? [];

  const actions = (
    <Button variant="outline" onClick={run} disabled={busy || !l}>
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />}
      {a ? "Re-assess" : "Assess lead"}
    </Button>
  );

  if (lead.error) return <ErrorState message={lead.error} onRetry={lead.reload} />;

  return (
    <>
      <PageHeader title={title}
        subtitle={l ? [l.job_title, l.company_name, l.company_location].filter(Boolean).join(" · ") : undefined}
        actions={actions} />
      {runError && <div className="mb-4"><ErrorState message={runError} /></div>}

      {assessment.error && !notAssessed && <ErrorState message={assessment.error} onRetry={assessment.reload} />}
      {notAssessed && (
        <Card className="p-6 text-center">
          <p className="font-semibold">This lead has not been assessed yet</p>
          <p className="mt-1 text-sm text-muted">Run the assessment to calculate its score and explanation.</p>
        </Card>
      )}
      {!a && !assessment.error && <div className="grid gap-4 md:grid-cols-3"><Skeleton className="h-64" /><Skeleton className="h-64 md:col-span-2" /></div>}

      {a && (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
            <Card className="flex flex-col items-center gap-3 p-5">
              <ScoreDial score={a.score} classification={a.classification}
                hot={a.config_snapshot.hot_threshold} warm={a.config_snapshot.warm_threshold} />
              <ClassificationBadge value={a.classification} className="text-sm px-3 py-1" />
              <ConfidenceBadge value={a.confidence_level} />
              <p className="text-center text-xs text-muted">Assessed {formatDate(a.assessed_at)}</p>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-3">
                <CardTitle>Lead quality assessment</CardTitle>
                <span className="inline-flex items-center gap-1 rounded-full bg-soft px-2.5 py-1 text-xs font-semibold text-muted">
                  <Sparkles className="size-3.5" aria-hidden />
                  {a.explanation_source === "gemini" ? `Written by Gemini` : "Rule-based text"}
                </span>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm leading-relaxed">{a.quality_assessment}</p>
                <div className="rounded-lg border-l-4 bg-soft p-4" style={{ borderColor: CLASS_COLOR[a.classification] }}>
                  <p className="text-sm font-semibold">Recommended next action</p>
                  <p className="mt-1 text-sm leading-relaxed">{a.recommended_next_action}</p>
                </div>
                {a.business_insights.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold">Business insights</p>
                    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">{a.business_insights.map((t) => <li key={t}>{t}</li>)}</ul>
                  </div>
                )}
                {a.gemini_error && (
                  <p className="flex items-start gap-2 text-xs text-muted">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
                    AI explanation unavailable ({a.gemini_error}). The score, breakdown and text above come from the built-in rules.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <Factors title="What raised the score" items={a.positive_factors} positive />
            <Factors title="What lowered the score" items={a.negative_factors} positive={false} />
          </div>

          <Card>
            <CardHeader><CardTitle>How the score was calculated</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-4">
                {a.breakdown.map((b) => (
                  <details key={b.parameter} className="group">
                    <summary className="cursor-pointer list-none">
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="font-semibold">{b.label}</span>
                        <span className="num font-semibold">{fmtScore(b.score)} <span className="font-normal text-muted">/ {b.max_score}</span></span>
                      </div>
                      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-soft">
                        <div className="h-full rounded-full bg-accent" style={{ width: `${b.max_score ? (b.score / b.max_score) * 100 : 0}%` }} />
                      </div>
                    </summary>
                    <div className="mt-2 space-y-1 rounded-md bg-soft p-3 text-[13px] text-muted">
                      <p><span className="font-semibold text-ink">Result:</span> {b.explanation}</p>
                      <p><span className="font-semibold text-ink">Criteria:</span> {b.criteria}</p>
                      <p><span className="font-semibold text-ink">Rule:</span> {b.rule_applied}</p>
                    </div>
                  </details>
                ))}
              </div>
              <p className="num mt-5 border-t border-line pt-4 text-sm font-semibold">
                {a.scoring_explanation.split("\n").at(-1)}
              </p>
              {a.explanation_source === "gemini" && <p className="mt-3 text-sm leading-relaxed text-muted">{a.ai_explanation}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4" aria-hidden /> Confidence in the data: {a.confidence_level.toLowerCase()} ({fmtScore(a.confidence_score)}/100)</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted">{a.confidence_details.disclaimer} It is calculated separately from the score.</p>
              <div className="grid gap-4 sm:grid-cols-2">
                {Object.entries(a.confidence_details.components).map(([k, c]) => (
                  <div key={k}>
                    <div className="flex justify-between text-sm"><span>{COMPONENT_LABELS[k] ?? k}</span><span className="num font-semibold">{fmtScore(c.score)} / {c.max}</span></div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-soft"><div className="h-full rounded-full bg-accent" style={{ width: `${(c.score / c.max) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
              {a.confidence_details.notes.length > 0 && (
                <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">{a.confidence_details.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {l && (
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>Submitted details</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[130px_1fr] gap-x-3 gap-y-2 text-sm">
                {([["Name", l.name], ["Company", l.company_name], ["Website", l.website], ["Job title", l.job_title], ["Industry", l.industry],
                  ["Location", l.company_location], ["Company size", l.company_size], ["Lead source", l.lead_source],
                  ["Requirement", l.requirement], ["Email", l.email], ["Phone", l.phone]] as [string, string | null][]).map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className={v ? "break-words" : "text-muted"}>{v ?? "Not provided"}</dd></div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-muted">Email, phone and website are checked for format only; none are verified.</p>
              {warnings.length > 0 && (
                <div className="mt-3 rounded-md bg-soft p-3 text-[13px] text-muted">
                  <p className="font-semibold text-ink">Notes</p>
                  <ul className="mt-1 list-disc pl-4">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                </div>
              )}
              {issues.length > 0 && (
                <div className="mt-4 rounded-md bg-warm-bg p-3 text-[13px] text-warm">
                  <p className="font-semibold">Missing or invalid fields</p>
                  <ul className="mt-1 list-disc pl-4">{issues.map((f) => <li key={f.field}>{f.label}: {f.status === "missing" ? "not provided" : f.message}</li>)}</ul>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Assessment history</CardTitle></CardHeader>
            <CardContent>
              {!history.data || history.data.length === 0 ? <p className="text-sm text-muted">No assessments yet.</p> : (
                <ul className="divide-y divide-line">
                  {history.data.map((h) => (
                    <li key={h.id} className="flex items-center justify-between py-2.5 text-sm">
                      <span className="text-muted">{formatDate(h.created_at)}</span>
                      <span className="flex items-center gap-3"><span className="num font-semibold">{fmtScore(h.score)}</span><ClassificationBadge value={h.classification} /></span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
      <p className="mt-6 text-sm"><Link href="/leads" className="font-semibold text-accent">← Back to leads</Link></p>
    </>
  );
}
