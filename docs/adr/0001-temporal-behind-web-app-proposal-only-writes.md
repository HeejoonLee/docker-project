# Temporal runs the work behind a separate web app; knowledge changes only through accepted Proposals

All ingestion, proposing, revision and maintenance run as Temporal workflows. Users touch only the Stonepedia web app, which talks to Temporal solely through its client API (start, signal, query, update) and never reads Temporal's database. The stock Temporal Web UI ships on a separate port as an admin/debug console. Nothing — not the agent, not a Maintenance check — writes to a Bundle except an Accept on a reviewed Article change, so every change in git has a human decision behind it.
