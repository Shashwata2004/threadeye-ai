"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useMe } from "@/lib/api/hooks";
import { permittedLanding } from "@/lib/pageAccess";
import { ghostBtn, useBi, ViewOnlyNote } from "@/components/screenKit";

export function PermissionNotice({title, children}: {title?: string; children?: ReactNode}) {
  const bi = useBi();
  const t = useTranslations("nav");
  const {data: me} = useMe();
  const pathname = usePathname();
  const target = permittedLanding(me, pathname);
  return <section className="space-y-3" data-testid="permission-notice">
    <ViewOnlyNote>
      <p className="font-semibold">{title ?? bi("Your account does not have permission to view this page.", "আপনার অ্যাকাউন্টে এই পেজ দেখার অনুমতি নেই।")}</p>
      <div>{children ?? bi("This does not mean there are no records. Ask an administrator if you need access for your work.",
        "এর অর্থ তথ্য নেই—এমন নয়। কাজের জন্য এই অংশ প্রয়োজন হলে অ্যাডমিনকে বলুন।")}</div>
    </ViewOnlyNote>
    <Link href={target.href} className={ghostBtn}>{bi("Go to: ", "যান: ")}{t(target.key)}</Link>
  </section>;
}
