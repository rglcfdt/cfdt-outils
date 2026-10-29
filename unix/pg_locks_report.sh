#!/usr/bin/env bash

set -u

RELATION="${1:-}"

if [ -z "$RELATION" ]; then
    echo "Usage:"
    echo "  $0 schema.table"
    echo
    echo "Exemple:"
    echo "  $0 index.index_egalite_fh"
    exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERREUR: psql n'est pas installé."
    exit 1
fi

REPORT_DIR="${REPORT_DIR:-/tmp}"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"

SAFE_RELATION="$(printf '%s' "$RELATION" | tr '. /' '___')"

REPORT_FILE="${REPORT_DIR}/pg_locks_${SAFE_RELATION}_${TIMESTAMP}.log"

exec > >(tee "$REPORT_FILE") 2>&1

echo "======================================================================"
echo " RAPPORT POSTGRESQL"
echo "======================================================================"
echo
echo "Date      : $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "Relation  : $RELATION"
echo "Serveur   : ${PGHOST:-non défini}"
echo "Port      : ${PGPORT:-5432}"
echo "Base      : ${PGDATABASE:-non définie}"
echo "Utilisateur: ${PGUSER:-non défini}"
echo
echo "Rapport   : $REPORT_FILE"
echo

run_sql() {
    local title="$1"
    local sql="$2"

    echo
    echo "======================================================================"
    echo " $title"
    echo "======================================================================"
    echo

    printf '%s\n' "$sql" |
        psql \
            -X \
            -v ON_ERROR_STOP=1 \
            -v relation="$RELATION" \
            -P pager=off \
            -P border=2
}

echo "Test de connexion PostgreSQL..."

if ! psql \
    -X \
    -v ON_ERROR_STOP=1 \
    -P pager=off \
    -c "SELECT current_database(), current_user, now();" \
    >/dev/null
then
    echo
    echo "ERREUR: connexion PostgreSQL impossible."
    exit 2
fi

echo "Connexion PostgreSQL OK."


run_sql \
"1 - Résolution de la relation" \
"
SELECT
    :'relation' AS relation_demandee,
    to_regclass(:'relation') AS relation_trouvee;
"


run_sql \
"2 - Sessions utilisant ou attendant la relation" \
"
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.backend_start,
    a.xact_start,
    a.query_start,
    now() - a.query_start AS duree_requete,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 500) AS query
FROM pg_stat_activity a
WHERE
       a.query ILIKE '%' || :'relation' || '%'
    OR cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY
    a.query_start NULLS LAST;
"


run_sql \
"3 - Verrous sur la relation" \
"
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.fastpath,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    a.query_start,
    now() - a.query_start AS duree_requete,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 500) AS query
FROM pg_locks l
LEFT JOIN pg_stat_activity a
       ON a.pid = l.pid
WHERE l.relation = to_regclass(:'relation')
ORDER BY
    l.granted,
    a.query_start NULLS LAST;
"


run_sql \
"4 - Relations bloquees et bloqueurs" \
"
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_application,
    blocked.state AS blocked_state,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.query_start AS blocked_since,

    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_application,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_transaction_start,
    blocker.query_start AS blocker_query_start,

    left(blocked.query, 500) AS blocked_query,
    left(blocker.query, 500) AS blocker_query

FROM pg_stat_activity blocked

CROSS JOIN LATERAL unnest(
    pg_blocking_pids(blocked.pid)
) AS p(blocker_pid)

JOIN pg_stat_activity blocker
  ON blocker.pid = p.blocker_pid

WHERE
       blocked.query ILIKE '%' || :'relation' || '%'
    OR blocker.query ILIKE '%' || :'relation' || '%'

ORDER BY blocked.query_start;
"


run_sql \
"5 - Transactions ouvertes" \
"
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start,
    query_start,
    now() - xact_start AS duree_transaction,
    now() - query_start AS duree_requete,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
"


run_sql \
"6 - Sessions idle in transaction" \
"
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    xact_start,
    state_change,
    now() - xact_start AS duree_transaction,
    left(query, 500) AS derniere_requete
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
"


run_sql \
"7 - COPY en cours" \
"
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS duree,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 700) AS query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND query ~* '^[[:space:]]*COPY[[:space:]]'
ORDER BY query_st*rt;
"


run_sql \
"8 - TRUNCATE en cours" \
"
SELECT
    pid,
    usename,
    app*ication_name,
    state,
    wait_*vent_type,
    wait_event,
    que*y_start,
    now() - query_start A* duree,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 700) AS query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND query ~* '^[[:space:]]*TRUNCATE[[:space:]]'
ORDER BY quer*_start;
"


run_sql \
"9 - Advisory locks" \
"
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.classid,
    l.objid,
    l.objsubid,
    l.mode,
    l.granted,
    a.xact_start,
    a.query_start,
    left(a.query, 500) AS query
FROM pg_locks l
LEFT JOIN pg_stat_activity a
       ON a.pid = l.pid
WHERE l.locktype = 'advisory'
ORDER BY l.pid;
"


run_sql \
"10 - Résumé des attentes PostgreSQL" \
"
SELECT
    wait_event_type,
    wait_event,
    count(*) AS nombre_sessions
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY
    wait_event_type,
    wait_event
ORDER BY
    count(*) DESC,
    wait_event_type,
    wait_event;
"

run_sql \
"11 - Sessions attendant le client" \
"
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - query_start AS duree,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 700) AS query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND wait_event_type = 'Client'
ORDER BY query_start;
"

echo
echo "======================================================================"
echo " RAPPORT TERMINE"
echo "======================================================================"
echo
echo "Fichier : $REPORT_FILE"


