# Judge access note

Hosted link: https://threadeye-web.vercel.app. Verify its deployed revision separately: local changes
are not automatically deployed. Never include .env.cloud or the database password in a submission.

The owner should share temporary demo-account credentials through the competition's private access
field. Accounts: store, inspector, supervisor, cutting, merchandiser, management, admin. Do not publish
the common demo password in the repository. Change temporary credentials after judging.

Recommended journey: store → register delivery and roll → inspector → inspect the simulated source,
review/add defects → finish and compute verdict → supervisor → decision and cutting approval → cutting
master → acknowledge → merchandiser → claim pack → management → scorecard/dashboard.

The reference-check and benchmark pages require a supervisor/admin to start a run. Benchmarking only
accepts a declared held-out test manifest. The current trained model can fail the reference tolerances;
this is shown honestly as RED. The answer-key-based perfect simulator is a software baseline, not AI.

Local real-model demonstration: run `make demo`, open http://localhost:3000. Requires internet for the
shared database. Offline product demonstration: Docker Compose with local model and source assets;
see README. All video remains simulated and is labelled accordingly.
