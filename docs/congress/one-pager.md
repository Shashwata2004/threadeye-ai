# ThreadEye AI

কাপড় পরীক্ষার স্মার্ট সহকারী — receiving inspection for garment factories.

**Problem:** find and document fabric faults before they become rejected garments or disputed mill claims.

**Journey:** roll registration → camera/video → detector → inspector review → 4-point verdict →
photo report → claim pack → approved cutting instructions → supplier scorecard.

**Architecture:** Next.js + FastAPI + PostgreSQL. YOLOX-S → ONNX Runtime CPU. Docker edge profile;
a separate Vercel/Supabase simulated cloud demonstration. Bangla and English. Append-only audit chain.

**Measured laboratory evidence:** current line-scan regression roll: 4 of 7 faults found, 0 false alarms.
One crease and two broken yarns are missed. Video is simulated. The regression roll has been reused in
development; these results do not establish factory-wide accuracy or business savings.

**Human control:** inspector confirms/rejects/adds faults; supervisor makes commercial and cutting decisions;
cutting master acknowledges instructions. Daily reference checks and benchmark history expose failures.

**Impact validation:** paired manual/assisted pilot protocol and calculator are available. Time saved,
usability gain, yield and financial savings are not claimed until measured.

**Demonstration:** https://threadeye-web.vercel.app (confirm deployed revision with the team).
Owner: Shashwata Nandi and the ThreadEye AI team.
