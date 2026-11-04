"use client";

import { useState } from "react";
import { errorDetail } from "@/lib/api/hooks";
import { ghostBtn, useBi } from "@/components/screenKit";

export function ClaimPackButton({lotId, disabled, testId = "claim-pack"}: {lotId: string; disabled?: boolean; testId?: string}) {
  const bi = useBi();
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    if (busy || disabled) return;
    setBusy(true); setReady(false); setError("");
    try {
      const response = await fetch(`/api/v1/lots/${lotId}/claim-pack.zip`, {credentials: "same-origin"});
      if (!response.ok) {
        const details = await response.json().catch(() => null);
        throw new Error(errorDetail(details, response.status));
      }
      if (!response.headers.get("content-type")?.includes("application/zip")) {
        throw new Error(bi("The server did not return a ZIP file.", "সার্ভার ZIP ফাইল দেয়নি।"));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = `claim-pack-${lotId}.zip`;
        document.body.appendChild(anchor); anchor.click(); anchor.remove();
        setReady(true);
      } finally { setTimeout(() => URL.revokeObjectURL(url), 60000); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <div className="space-y-1">
    <button type="button" className={`${ghostBtn} px-2 py-1 text-xs`} disabled={disabled || busy}
      onClick={() => void download()} data-testid={testId}>
      {busy ? bi("Preparing ZIP…", "ZIP প্রস্তুত হচ্ছে…") : bi("Claim pack (ZIP)", "ক্লেইম প্যাক (ZIP)")}
    </button>
    {ready && !disabled && <p role="status" className="text-xs text-brand-teal">{bi("ZIP ready; download started", "ZIP প্রস্তুত; ডাউনলোড শুরু হয়েছে")}</p>}
    {error && <p role="alert" className="max-w-sm text-xs text-red-600">{bi("Claim pack could not be created: ", "ক্লেইম প্যাক তৈরি হয়নি: ")}{error}</p>}
  </div>;
}
