# ThreadEye: impact মাপার পদ্ধতি

এখনকার `REPORT.md` হলো simulated video-তে বাস্তব model-এর measured replay। মানুষের সঙ্গে তুলনা,
factory yield বা টাকা সাশ্রয়ের প্রমাণ এখনো নেই। `evidence.json`-এ input/model/code hash ও machine details আছে।
পুরোনো ফল সংরক্ষণ করতে প্রতিবার আলাদা `--out` directory দিন; `make impact` বর্তমান report প্রতিস্থাপন করে।

## ১. পুনরায় model replay চালানো

Repo root থেকে, Python environment-এ `onnx` extra এবং model/video assets থাকা অবস্থায়:

```bash
make impact
# অথবা আলাদা output folder:
backend/.venv/bin/python scripts/measure_impact.py --out build/impact-new
```

এতে database, Supabase বা কোনো account লাগে না। Training হয় না, model/video বদলায় না।
Report-এ model-only score ও answer-key score একই 4-point profile-এ তুলনা হয়। Model-এর সব detection
auto-confirm করার অনুমান স্পষ্টভাবে লেখা থাকে; এটি মানুষের সিদ্ধান্তের রেকর্ড নয়। Model load,
video decode ও inference-এর headless সময়কে inspection time saving বলা যাবে না।

## ২. Manual বনাম assisted pilot

1. আগে ব্যবহার না করা একাধিক roll বাছুন; light/dark/patterned fabric ও বিভিন্ন defect অন্তর্ভুক্ত করুন।
   প্রথম pilot-এ অন্তত ১০টি paired roll লক্ষ্য রাখুন; ছোট নমুনা থেকে factory-wide দাবি করবেন না।
2. দুইজন অভিজ্ঞ reviewer model prediction না দেখে প্রতিটি roll-এর defect location, type ও size
   মিলিয়ে independent answer key তৈরি করবেন। মতভেদ মিটিয়ে তারপর ফল তুলনা করুন।
3. একই roll দুই অবস্থায় পরীক্ষা করুন: `manual` = AI ছাড়া, `assisted` = AI ও inspector review সহ।
   আলাদা inspector ব্যবহার করুন, অথবা order counterbalance করুন এবং memory/order effect লিখে রাখুন।
   Operator, speed, lighting, hardware, method order ও session date আলাদা pilot notes-এ রাখুন।
4. দুই অবস্থায় একই শুরু/শেষ সংজ্ঞা নিন: roll load থেকে review ও final report প্রস্তুত হওয়া পর্যন্ত
   wall-clock seconds। Model inference time দিয়ে এই ঘর পূরণ করবেন না।
5. একই ground-truth matching rule আগে ঠিক করুন। Final inspection-এ কত defect বাদ গেছে এবং কত
   ভুল defect রয়ে গেছে লিখুন। `assisted` ফল বলতে human-corrected final result বোঝাবে।
6. `pilot-template.csv` কপি করে প্রতি roll-এ দুটি row পূরণ করুন। Roll ID হিসেবে অনামিক code ব্যবহার করুন।
   সংখ্যা না মাপলে optional `usable_yd` ও `loss_bdt` খালি রাখুন; আন্দাজ বা zero লিখবেন না।
7. `usable_yd` কেবল একই specification অনুযায়ী independently যাচাই করা usable fabric হলে দিন।
   `loss_bdt` actual, documented loss হলে দিন, একই accounting boundary-তে। একই বাস্তব কাপড়ের দুইটি
   counterfactual outcome মাপা সম্ভব না হলে এগুলো খালি রাখুন; hypothetical ROI-কে pilot data করবেন না।

Columns: `roll_id`, `method`, `seconds`, `truth_defects`, `missed_defects`, `false_alarms`,
optional `usable_yd`, optional `loss_bdt`। কোনো customer/inspector পরিচয় বা private invoice repository-তে দেবেন না।

```bash
backend/.venv/bin/python scripts/measure_impact.py \
  --pilot-csv /path/to/measured-pilot.csv --out build/impact-pilot
```

## ৩. হিসাব ও দাবির সীমা

- Time reduction = `(total manual seconds − total assisted seconds) / total manual seconds × 100`।
- Missed-defect reduction = `(manual misses − assisted misses) / manual misses × 100`। Manual misses
  শূন্য হলে percentage undefined; শূন্য বা ১০০% উন্নতি বলে দেখানো হবে না।
- Usable gain = total assisted usable yards − total manual usable yards।
- Loss reduction = total manual loss BDT − total assisted loss BDT।
- Negative ফল মানে assisted ফল খারাপ। কোনো paired observation বাদ দেবেন না। সব row-তে yield বা
  loss না মাপলে ওই aggregate unknown থাকবে। Template খালি থাকলে tool impact claim তৈরি করবে না।

Submission-এ sample size, collection notes, raw anonymous observations, unchanged input hashes এবং
limitations সংযুক্ত করুন। ছোট pilot-এর descriptive totals causal proof বা validated production ROI নয়।
