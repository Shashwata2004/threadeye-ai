"""Initial editable narrative and owner-supplied DU_Synapse team details."""

from threadeye.api.schemas.docs import DocsConfig, DocsSection, DocsText


def text(en: str, bn: str) -> DocsText:
    return DocsText(en=en, bn=bn)


def default_config() -> DocsConfig:
    sections = [
        (
            "problem",
            "The problem",
            "সমস্যা",
            (
                "Fabric inspection decisions are often separated from defect photos, buyer scoring "
                "rules and cutting instructions. Teams need traceable evidence before accepting fabric"
                " or sending it to cutting."
            ),
            (
                "কাপড়ের ত্রুটির ছবি, বায়ারের স্কোরিং নিয়ম ও কাটিং নির্দেশনা অনেক সময় আলাদা থাকে। কাপড় "
                "গ্রহণ বা কাটিংয়ে পাঠানোর আগে দলের নির্ভরযোগ্য প্রমাণ দরকার।"
            ),
        ),
        (
            "solution",
            "Our solution",
            "আমাদের সমাধান",
            (
                "ThreadEye connects receiving, trained visual detection, inspector correction, four-"
                "point scoring, supervisor decisions, cutting directions and supplier claim evidence "
                "in one workflow."
            ),
            (
                "ThreadEye চালান গ্রহণ, প্রশিক্ষিত মডেলের শনাক্তকরণ, ইন্সপেক্টরের সংশোধন, চার-পয়েন্ট "
                "স্কোর, সুপারভাইজারের সিদ্ধান্ত, কাটিং নির্দেশনা ও ক্লেইমের প্রমাণ একসঙ্গে রাখে।"
            ),
        ),
        (
            "users",
            "Who it serves",
            "কারা ব্যবহার করেন",
            (
                "Inspectors review defects. QC supervisors decide roll acceptance. Store staff receive"
                " and label rolls. Cutting masters acknowledge approved directions. Merchandisers "
                "prepare claims; management reviews aggregate performance."
            ),
            (
                "ইন্সপেক্টর ত্রুটি যাচাই করেন, QC সুপারভাইজার গ্রহণের সিদ্ধান্ত দেন। স্টোর চালান ও "
                "রোলের লেবেল করেন। কাটিং মাস্টার নির্দেশনা গ্রহণ করেন। মার্চেন্ডাইজার ক্লেইম এবং "
                "ম্যানেজমেন্ট সামগ্রিক ফল দেখেন।"
            ),
        ),
        (
            "product",
            "Product and workflow",
            "পণ্যের কাজের ধাপ",
            (
                "A challan contains multiple rolls. Register and QR-label each roll, inspect its "
                "footage, confirm or reject AI flags, draw boxes for missed defects, then finalize "
                "scoring and the human decision. Approved cutting plans and acknowledgements remain "
                "traceable."
            ),
            (
                "একটি চালানে একাধিক রোল থাকে। প্রতিটির তথ্য ও QR লেবেল তৈরি, ভিডিও পরীক্ষা, AI সতর্কতা"
                " গ্রহণ/বাতিল এবং বাদ পড়া ত্রুটিতে বক্স আঁকা যায়। এরপর স্কোর ও মানুষের সিদ্ধান্ত "
                "সংরক্ষণ হয়। অনুমোদিত কাটিং ও গ্রহণের স্বীকৃতিও খুঁজে দেখা যায়।"
            ),
        ),
        (
            "market",
            "Users and adoption path",
            "ব্যবহারকারী ও প্রয়োগের পথ",
            (
                "The initial focus is garment-factory receiving and fabric QC teams. The adoption path"
                " is a supervised pilot: compare inspection time, missed defects, usable yardage and "
                "claim preparation against the factory's own baseline."
            ),
            (
                "প্রথম লক্ষ্য পোশাক কারখানার কাপড় গ্রহণ ও QC দল। পরীক্ষামূলক প্রয়োগে কারখানার আগের "
                "হিসাবের সঙ্গে পরীক্ষার সময়, বাদ পড়া ত্রুটি, ব্যবহারযোগ্য গজ ও ক্লেইম তৈরির সময় তুলনা "
                "করা হবে।"
            ),
        ),
        (
            "business",
            "Deployment and value",
            "প্রয়োগ ও উপযোগিতা",
            (
                "An edge deployment supports local CPU inference and offline operation; the cloud demo"
                " offers remote access. Value comes from consistent scoring, evidence-backed decisions"
                " and defect-aware cutting. Factory savings depend on measured pilot results."
            ),
            (
                "এজ সংস্করণে স্থানীয় CPU inference ও অফলাইন কাজের ব্যবস্থা; cloud demo দূর থেকে দেখা "
                "যায়। একই নিয়মে স্কোর, প্রমাণসহ সিদ্ধান্ত ও ত্রুটি অনুযায়ী কাটিং কাজে সহায়তা করে। "
                "আর্থিক সাশ্রয় কারখানায় পরিমাপ করে নির্ধারণ করতে হবে।"
            ),
        ),
        (
            "model",
            "AI and data provenance",
            "AI ও ডেটার উৎস",
            (
                "The trained YOLOX-S detector runs through ONNX Runtime on CPU. Demo camera footage is"
                " simulated; the active detector is disclosed separately below. The alternative "
                "simulated detector reads an answer key. Inspector edits are exportable review data, "
                "not automatic online learning. The companion evidence assistant uses embeddings and "
                "deterministic extraction."
            ),
            (
                "প্রশিক্ষিত YOLOX-S detector ONNX Runtime দিয়ে CPU-তে চলে। Demo ক্যামেরার ভিডিও "
                "সিমুলেটেড; সক্রিয় detector আলাদা করে নিচে দেখানো হয়। বিকল্প simulated detector answer"
                " key পড়ে। ইন্সপেক্টরের সংশোধন review data হিসেবে export হয়, তাৎক্ষণিক training নয়। "
                "আলাদা evidence assistant embeddings ও deterministic extraction ব্যবহার করে।"
            ),
        ),
        (
            "stack",
            "Technical stack",
            "প্রযুক্তি",
            (
                "Next.js, React, TypeScript and next-intl power the web app. FastAPI, SQLAlchemy and "
                "PostgreSQL serve authenticated operations. ONNX Runtime handles detection; Recharts, "
                "Chart.js, ECharts and Plotly visualize existing operational and evaluation data. "
                "Docker/Caddy support edge deployment; Vercel hosts the cloud frontend and API."
            ),
            (
                "ওয়েব অ্যাপে Next.js, React, TypeScript ও next-intl। FastAPI, SQLAlchemy ও PostgreSQL "
                "দিয়ে অনুমতিভিত্তিক কাজ চলে। ONNX Runtime শনাক্তকরণ করে। Recharts, Chart.js, ECharts ও"
                " Plotly বর্তমান ফল দেখায়। Docker/Caddy এজে এবং Vercel cloud frontend ও API চালায়।"
            ),
        ),
        (
            "security",
            "Security and accountability",
            "নিরাপত্তা ও জবাবদিহি",
            (
                "Server-side permissions separate operational roles. Session cookies authenticate "
                "users; consequential changes produce hash-linked audit records. Inspection model/rule"
                " snapshots and signed decisions remain historical. Public documentation exposes "
                "aggregate counts, not user records or defect evidence."
            ),
            (
                "সার্ভারে অনুমতি যাচাই করে দায়িত্ব আলাদা রাখা হয়। Session cookie দিয়ে লগইন এবং "
                "গুরুত্বপূর্ণ পরিবর্তনে hash-linked audit থাকে। পরীক্ষার মডেল/নিয়ম ও সিদ্ধান্তের "
                "ইতিহাস সংরক্ষিত থাকে। Public docs-এ শুধু সামগ্রিক সংখ্যা, ব্যক্তিগত রেকর্ড বা ত্রুটির"
                " প্রমাণ নয়।"
            ),
        ),
        (
            "validation",
            "Validation and measurement",
            "যাচাই ও পরিমাপ",
            (
                "Evaluation reports distinguish localization recall, correct-class recall, precision "
                "and false alerts. Reference-video checks assess software-pipeline behavior, not "
                "physical camera calibration. Roll-demo regression results and overall dataset results"
                " answer different questions."
            ),
            (
                "মূল্যায়নে ত্রুটির অবস্থান ধরা, সঠিক শ্রেণি, precision ও ভুল সতর্কতা আলাদা থাকে। "
                "রেফারেন্স ভিডিও সফটওয়্যার pipeline যাচাই করে, বাস্তব ক্যামেরার calibration নয়। রোল "
                "demo regression ও পুরো dataset-এর ফলের অর্থ আলাদা।"
            ),
        ),
        (
            "roadmap",
            "Next steps",
            "পরবর্তী কাজ",
            (
                "Improve thin broken-yarn detection, review inspector corrections for future "
                "retraining, and run factory pilots with measured baselines. Candidate models must "
                "pass production-pipeline checks before activation; existing inspections retain their "
                "original model identity."
            ),
            (
                "সরু ছেঁড়া সুতা শনাক্তকরণ উন্নত করা, ভবিষ্যৎ retraining-এর জন্য সংশোধিত data review "
                "এবং মাপা baseline-সহ কারখানায় pilot চালানো। নতুন model চালুর আগে production pipeline "
                "যাচাই হবে; পুরোনো পরীক্ষার model identity অপরিবর্তিত থাকবে।"
            ),
        ),
    ]
    content = [
        DocsSection(id=key, title=text(title, title_bn), body=text(body, body_bn))
        for key, title, title_bn, body, body_bn in sections
    ]
    content.insert(
        4,
        DocsSection(
            id="architecture",
            title=text("System architecture", "সিস্টেমের গঠন"),
            body=text(
                "The API connects the browser to persistent records and the CPU detector.",
                "API ব্রাউজারকে স্থায়ী রেকর্ড ও CPU detector-এর সঙ্গে যুক্ত করে।",
            ),
            diagram="architecture",
            steps=[
                text("Browser · Next.js", "ব্রাউজার · Next.js"),
                text("API · FastAPI", "API · FastAPI"),
                text("Database · PostgreSQL", "ডাটাবেজ · PostgreSQL"),
                text("Detector · ONNX CPU", "Detector · ONNX CPU"),
            ],
        ),
    )
    content.insert(
        5,
        DocsSection(
            id="data-flow",
            title=text("Inspection data flow", "পরিদর্শনের তথ্যপ্রবাহ"),
            body=text(
                "Video pixels feed detection; human review precedes scoring and decisions.",
                "ভিডিওর pixels থেকে শনাক্তকরণ; স্কোর ও সিদ্ধান্তের আগে মানুষ যাচাই করেন।",
            ),
            diagram="inspection",
            steps=[
                text("Video frame", "ভিডিও ফ্রেম"),
                text("Detector", "শনাক্তকরণ"),
                text("Inspector review", "ইন্সপেক্টরের যাচাই"),
                text("Four-point scoring", "চার-পয়েন্ট স্কোর"),
                text("Supervisor decision", "সুপারভাইজারের সিদ্ধান্ত"),
                text("Evidence & cutting", "প্রমাণ ও কাটিং"),
            ],
        ),
    )
    members = [
        ("shashwata", "Shashwata Nandi", "Backend & AI Integration", "Backend ও AI সংযোগ", "nandisantu274@gmail.com"),
        ("fahmid", "Mohammad Mahmudul Kabir Fahmid", "Frontend", "Frontend", "gmahmud1944@gmail.com"),
        ("turja", "Arin Saha Turja", "Testing & Presentation", "যাচাই ও উপস্থাপনা", "turja2k21@gmail.com"),
        ("jahin", "Abshary Jahin", "UI/UX", "UI/UX", "abshary-2025815502@cs.du.ac.bd"),
        (
            "rupanty",
            "Rupanty Saha",
            "Documentation & Demo Support",
            "নথি ও Demo সহায়তা",
            "rupanty-2025515523@cs.du.ac.bd",
        ),
    ]
    return DocsConfig(
        tagline=text("From fabric defects to traceable decisions.", "কাপড়ের ত্রুটি থেকে প্রমাণসহ সিদ্ধান্ত।"),
        repository_url="https://github.com/Shashwata2004/threadeye-ai",
        app_url="https://threadeye-web.vercel.app",
        video_url="https://youtu.be/dFBMcYwV3NI",
        sections=content,
        members=[
            {"id": key, "name": name, "role": text(role, role_bn), "email": email}
            for key, name, role, role_bn, email in members
        ],
    )
