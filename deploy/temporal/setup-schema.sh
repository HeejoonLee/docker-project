#!/bin/sh
# Create or upgrade Temporal's Postgres schemas. Safe to run on every start.
set -eu
T="temporal-sql-tool --plugin postgres12 --ep postgres -u temporal -p 5432"
for db in temporal temporal_visibility; do
  dir=temporal; [ "$db" = temporal_visibility ] && dir=visibility
  $T --db $db create 2>/dev/null || true
  $T --db $db setup-schema -v 0.0 2>/dev/null || true
  $T --db $db update-schema -d /etc/temporal/schema/postgresql/v12/$dir/versioned
done
echo "Temporal schema ready"
