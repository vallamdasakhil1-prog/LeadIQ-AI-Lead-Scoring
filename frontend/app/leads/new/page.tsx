"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader } from "@/components/states";
import { api, ApiError, type LeadInput } from "@/lib/api";

const SAMPLE: LeadInput = {
  name: "Rahul Sharma", company_name: "ABC Technologies", website: "www.abctechnologies.com",
  job_title: "Founder", industry: "IT Services", company_location: "Bangalore",
  company_size: "50–100 Employees", lead_source: "Website", requirement: "Looking for CRM software",
  email: "rahul@example.com", phone: "+91 9876543210",
};

type Key = keyof LeadInput;
const FIELDS: { key: Key; label: string; placeholder: string; type?: string; full?: boolean; hint?: string }[] = [
  { key: "name", label: "Name", placeholder: "Rahul Sharma" },
  { key: "company_name", label: "Company name", placeholder: "ABC Technologies" },
  { key: "website", label: "Website", placeholder: "www.abctechnologies.com" },
  { key: "job_title", label: "Job title", placeholder: "Founder" },
  { key: "industry", label: "Industry", placeholder: "IT Services" },
  { key: "company_location", label: "Company location", placeholder: "Bangalore" },
  { key: "company_size", label: "Company size", placeholder: "50–100 employees", hint: "A number or range, e.g. 50-100 or 1000+" },
  { key: "lead_source", label: "Lead source", placeholder: "Website, Referral, LinkedIn…" },
  { key: "email", label: "Email", placeholder: "rahul@example.com", type: "email" },
  { key: "phone", label: "Phone", placeholder: "+91 9876543210", type: "tel", hint: "10-digit numbers are treated as Indian (+91)" },
  { key: "requirement", label: "Requirement", placeholder: "What is the lead looking for?", full: true },
];

function Form() {
  const router = useRouter();
  const sp = useSearchParams();
  const [values, setValues] = useState<LeadInput>(sp.get("sample") ? SAMPLE : {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = (k: Key, v: string) => setValues((s) => ({ ...s, [k]: v }));
  const hasIdentity = Boolean(values.name?.trim() || values.company_name?.trim());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    setFieldErrors({});
    if (!hasIdentity) {
      setError("Enter at least a contact name or a company name so the lead can be identified.");
      return;
    }
    setBusy(true);
    let leadId: number | undefined;
    try {
      const created = await api.createLead(Object.fromEntries(Object.entries(values).filter(([, v]) => v?.trim())));
      leadId = created.lead.id;
      await api.assess(leadId);
      router.push(`/leads/${leadId}`);
    } catch (err) {
      if (leadId) { router.push(`/leads/${leadId}`); return; } // lead saved; assessment page offers a retry
      const ae = err as ApiError;
      if (ae.validation) {
        setFieldErrors(Object.fromEntries(ae.validation.fields.filter((f) => f.status === "invalid").map((f) => [f.field, f.message])));
      }
      setError(ae.message ?? "Could not submit the lead.");
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Add lead" subtitle="Every field is optional except a name or company. Missing details lower the score and confidence; they never block a lead."
        actions={<Button variant="outline" type="button" onClick={() => setValues(SAMPLE)}>Fill sample lead</Button>} />
      <form onSubmit={submit} noValidate>
        <Card>
          <CardContent className="grid gap-5 pt-5 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <div key={f.key} className={f.full ? "sm:col-span-2" : ""}>
                <Label htmlFor={f.key}>{f.label}</Label>
                {f.full ? (
                  <Textarea id={f.key} className="mt-1.5" placeholder={f.placeholder} value={values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
                ) : (
                  <Input id={f.key} className="mt-1.5" type={f.type === "email" ? "text" : f.type} inputMode={f.type === "tel" ? "tel" : f.type === "email" ? "email" : undefined}
                    placeholder={f.placeholder} value={values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)}
                    aria-invalid={Boolean(fieldErrors[f.key])} aria-describedby={`${f.key}-help`} />
                )}
                <p id={`${f.key}-help`} className={fieldErrors[f.key] ? "mt-1 text-xs text-neg" : "mt-1 text-xs text-muted"}>
                  {fieldErrors[f.key] ?? f.hint ?? ""}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
        {error && <div className="mt-4"><ErrorState message={error} /></div>}
        <div className="mt-5 flex items-center gap-3">
          <Button type="submit" disabled={busy}>
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden />} {busy ? "Scoring…" : "Score lead"}
          </Button>
          <p className="text-sm text-muted">The score comes from fixed rules; AI then writes the explanation.</p>
        </div>
      </form>
    </>
  );
}

export default function AddLeadPage() {
  return <Suspense><Form /></Suspense>;
}
