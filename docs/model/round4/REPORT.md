# Round four: renderer-matched pilot-এর ফল

**সিদ্ধান্ত: pilot ব্যর্থ। ৮-epoch final training শুরু হয়নি; অ্যাপে আগের মডেল চালু আছে।**

একই Kaggle dataset ও round-two checkpoint ব্যবহার করে ৬,০০০ training frame এবং ১,০০০ আলাদা validation frame-এ দুই epoch fine-tuning করা হয়েছে। Actual DatasetSource/RollRenderer এবং ভিডিওর shared camera-effect code দিয়ে target/clean frame তৈরি হয়েছে। ৫০% target, ৩০% পুরোনো replay, ২০% clean অনুপাত রাখা হয়েছে।

## পুরোনো চার ভিডিও

| মডেল | অবস্থান মিলেছে | ভুল সতর্কতা | সঠিক class-এ broken yarn |
|---|---:|---:|---:|
| অ্যাপে থাকা baseline (আগের মাপ) | 19/30 | 18 | 0/7 |
| Round two (আগের মাপ) | 23/30 | 14 | 0/7 |
| Round three (আগের মাপ) | 18/30 | 12 | 0/7 |
| এই pilot, laptop CPU | 10/30 | 169 | 0/7 |

এই pilot-এর ১০টি positional match-এর মধ্যে 8টির class-ও সঠিক। Ground-truth matching protocol আগেরটিই রাখা হয়েছে।

| ভিডিও | TP | FP | FN | সঠিক broken yarn | CPU সময় / ভিডিও সময় |
|---|---:|---:|---:|---:|---:|
| linescan_roll | 2 | 16 | 5 | 0/2 | 0.775 |
| demo_basic_roll | 1 | 125 | 2 | 0/0 | 0.873 |
| demo_mixed_roll | 3 | 2 | 6 | 0/2 | 0.786 |
| demo_challenge_roll | 4 | 26 | 7 | 0/3 | 0.658 |

## আলাদা validation ভিডিও

| মাপ | Round three | এই pilot |
|---|---:|---:|
| অবস্থানভিত্তিক recall | 64/120 (53.33%) | 55/120 (45.83%) |
| Precision | 40.76% | 40.15% |
| সঠিক class-এ broken yarn | 14/29 (48.28%) | 17/29 (58.62%) |
| ভুল সতর্কতা | 93 | 82 |

এই pilot-এর validation ভিডিওতে 49/120 ত্রুটি অবস্থান ও class উভয় হিসেবে সঠিক। চারটি validation ভিডিওর বিস্তারিত PILOT_REPORT.md ও pilot-cpu-val_*.json-এ আছে।

Broken-yarn-এর একটি মাপে উন্নতি হয়েছে, কিন্তু সামগ্রিক recall/precision ও পুরোনো ভিডিওর ফল খারাপ হওয়ায় pilot gate পাস হয়নি।

নতুন native image validation-এ precision 86.98%, recall 54.65%, সঠিক-class broken-yarn recall 55.07%। Round-three native validation-এর সঙ্গে এই শতাংশ সরাসরি তুলনাযোগ্য নয়: training/validation frame generator ও input shape বদলেছে। Image precision ভালো হলেই ভিডিওতে ভালো ফল হয় না।

## সাতটি missed broken-yarn-এর diagnosis

| ভিডিও / truth ID | ধাপ | সর্বোচ্চ broken-yarn score | threshold |
|---|---|---:|---:|
| demo_challenge_roll / 6 | tracking_or_geometry | 0.4879 | 0.18 |
| demo_challenge_roll / 8 | tracking_or_geometry | 0.6655 | 0.18 |
| demo_challenge_roll / 11 | tracking_or_geometry | 0.6667 | 0.18 |
| linescan_roll / 5 | threshold | 0.1701 | 0.18 |
| linescan_roll / 7 | no_usable_prediction | 0.0059 | 0.18 |
| demo_mixed_roll / 4 | threshold | 0.0119 | 0.18 |
| demo_mixed_roll / 7 | threshold | 0.0824 | 0.18 |

Production sampling এবং প্রতিটি দৃশ্যমান frame—দুই replay-তেই এই সাতটির যোগ্য track পাওয়া যায়নি। Challenge ভিডিওর বড় horizontal defect-এ অংশবিশেষ prediction থাকলেও geometry/tracking association ব্যর্থ হচ্ছে। Threshold-এর নিচের score এবং অনুপস্থিত prediction-কে একই সমস্যা বলা হয়নি। Regression ভিডিও দেখে threshold নামানো হয়নি।

## Data থেকে পাওয়া সীমাবদ্ধতা

- AITEX subtype 006-এর training অংশে একটি মূল ছবিই আছে; inspected দৃশ্যে সেটি চওড়া বাঁকানো ত্রুটি। পুরোনো ভিডিওতে ব্যবহৃত 0014/0015/0016_006_02 মূল ছবি test অংশে; সেগুলো training-এ নেওয়া হয়নি।
- বর্তমান rendered training-এ সরু vertical AITEX broken-yarn donor হলো 0090_002_01; এটি 006 subtype-এর নতুন উদাহরণ নয়। অন্য source-এর narrow morphology একই ধরনের বাস্তব ছেঁড়া সুতা—এমন নিশ্চয়তা নেই।
- একই ছবির variant ও মূল ছবির সংখ্যা আলাদা রাখা হয়েছে। Metadata-তে প্রতিটি donor/background/reference original ও group আছে; training/validation group disjoint checks পাস।
- Moratuwa/Tianchi-র কিছু rendered দৃশ্যে tile join আছে। JPEG frame দিয়ে training হয়েছে; H.264 compression ও hand occlusion এই generator-এ পুরোপুরি অনুকরণ হয়নি।
- এসব data mismatch ব্যর্থতার সম্ভাব্য কারণ; একক controlled ablation ছাড়া কোনটির অবদান কত তা প্রমাণিত বলা যাবে না।

## কী সংরক্ষিত / কী চালানো হয়নি

- Native 320x640 pilot checkpoint/ONNX private Kaggle output-এ সংরক্ষিত। Model card: pilot-model-card.json; model ও input/provenance hash: result.json।
- Whole-strip/overlapping tiles, stitching on/off শুধু held-out validation ভিডিও দিয়ে বাছা হয়েছে। Selected mode whole-strip 1x, stitching off। GPU ও laptop CPU-র aggregate TP/FP/broken-yarn ফল এক।
- চারটি frozen final-test ভিডিও খোলা হয়নি। এই pilot-এ পুরোনো overall dataset test পুনরায় চালানো হয়নি; আগের overall ফল round3/REPORT.md-এ আছে।
- Pilot ব্যর্থ হওয়ায় বড় training, deployment বা historical inspection বদলানো হয়নি। বর্তমান API ও frontend HTTP 200 এবং installed model hash অপরিবর্তিত।

## পরের কার্যকর data প্রয়োজন

একই ধূসর weave-এ সরু vertical broken yarn-এর একাধিক স্বাধীন training original ও সঠিক mask দরকার; অন্তত আলাদা roll/session থেকে clean negative, slub ও crease-সহ উদাহরণ থাকতে হবে। বিদ্যমান test donor training-এ এনে উন্নতি দাবি করা যাবে না। একই ছবি আরও বার নকল করে বা শুধু epoch বাড়িয়ে এই ঘাটতি পূরণ হয়েছে বলা যাবে না। এই রিপোর্টের পরে নতুন training শুরু করা হয়নি।

Verification: 10 scoped ML tests, scoped Ruff এবং git diff --check পাস; shared renderer arithmetic bitwise parity পাস।
