"use client";

import { useModelEvaluation, useProviders, useSystemStatus } from "@/lib/api/hooks";
import { Card, CardTitle, PageHeader, screenRoot, useBi } from "@/components/screenKit";

export default function AboutPage() {
  const bi = useBi();
  const {data: status} = useSystemStatus();
  const {data: providers} = useProviders();
  const {data: model} = useModelEvaluation();
  return <div className={`${screenRoot} space-y-4`}>
    <PageHeader title={bi("About and provenance", "পরিচিতি ও তথ্যের উৎস")} sample={false}
      subtitle={bi("Know what is simulated, which detector is running and where evidence comes from.",
        "কোন অংশ সিমুলেটেড, কোন শনাক্তকারী চলছে ও প্রমাণের উৎস জানুন।")}/>
    <Card><CardTitle>{bi("This deployment", "এই সংস্করণ")}</CardTitle>
      <p>{bi("Version", "সংস্করণ")}: {status?.version ?? "—"} · {status?.profile ?? "—"}</p>
      <p>{bi("All available roll video is simulated. The source is disclosed independently of the detector.",
        "উপলব্ধ রোলের ভিডিওগুলো সিমুলেটেড। ভিডিওর উৎস ও শনাক্তকারীর পরিচয় আলাদাভাবে দেখানো হয়।")}</p>
      {providers?.filter((p) => p.active).map((p) => <p key={p.provider_id}>{p.display_name} · {p.is_simulated ?
        bi("Answer-key simulation, not AI", "উত্তর-চাবিভিত্তিক সিমুলেশন, AI নয়") : bi("Trained local model", "নিজের ট্রেন করা মডেল")}</p>)}
    </Card>
    <Card><CardTitle>{bi("Data and model", "ডেটা ও মডেল")}</CardTitle>
      <p>{model ? `${model.model} · ${model.epochs} epochs` : bi("No evaluated model card available.", "মূল্যায়িত মডেলের তথ্য নেই।")}</p>
      <p>{bi("Public fabric datasets and generated distractions support training. Source images, crops and duplicates are grouped before splitting.",
        "পাবলিক কাপড়ের ডেটাসেট ও তৈরি করা অ-ত্রুটির উদাহরণ দিয়ে training করা হয়। উৎসের ছবি, crop ও duplicate একই ভাগে রাখা হয়।")}</p>
      <p>{bi("AITEX redistribution terms and some original-source licences still need confirmation before public redistribution. Detailed sources and credits are recorded in PROVENANCE.md and ml/DATASETS.md in the repository.",
        "পাবলিক বিতরণের আগে AITEX ও কিছু মূল উৎসের অনুমতি নিশ্চিত করতে হবে। বিস্তারিত উৎস ও স্বীকৃতি repository-এর PROVENANCE.md ও ml/DATASETS.md-তে আছে।")}</p>
    </Card>
    <Card><CardTitle>{bi("Limits and human control", "সীমাবদ্ধতা ও মানুষের নিয়ন্ত্রণ")}</CardTitle>
      <p>{bi("A reference-video check does not certify a physical camera. A model benchmark does not prove factory savings. Paired human observations are required for impact claims.",
        "রেফারেন্স ভিডিওর পরীক্ষা বাস্তব ক্যামেরার নিশ্চয়তা নয়। মডেলের বেঞ্চমার্ক কারখানার সাশ্রয়ের প্রমাণ নয়। impact দাবির জন্য মানুষের তুলনামূলক পরীক্ষা প্রয়োজন।")}</p>
      <p>{bi("Inspector corrections can be exported for review. They do not automatically retrain or replace the installed model.",
        "ইন্সপেক্টরের সংশোধন যাচাইয়ের জন্য export করা যায়। এতে চলমান মডেল নিজে থেকে train বা বদলে যায় না।")}</p>
    </Card>
  </div>;
}
