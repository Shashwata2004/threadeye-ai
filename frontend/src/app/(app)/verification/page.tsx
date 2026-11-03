"use client";

import { EvaluationWorkbench } from "@/components/EvaluationWorkbench";
import { PageHeader, screenRoot, useBi } from "@/components/screenKit";

export default function Page() {
  const bi = useBi();
  return <div className={`${screenRoot} space-y-5`}>
    <PageHeader title={bi("Daily verification", "দৈনিক যাচাই")} sample={false}
      subtitle={bi("Reference roll, measured tolerances and saved history.", "রেফারেন্স রোল, নির্ধারিত সীমা ও সংরক্ষিত ফলাফল।")}/>
    <EvaluationWorkbench kind="verification"/>
  </div>;
}
