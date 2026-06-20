#!/usr/bin/env bash

OLD_MINUTES=30
START_MS_TS="$(($(date +%s%N)/1000000 - ${OLD_MINUTES}*60*1000))"

WHERE_CLAUSE="WHERE stream.favorite != true AND stream.end_timestamp < ${START_MS_TS}"

# No ON DELETE CASCADE :(
COMMAND="
CREATE TEMP TABLE removed_id AS SELECT id FROM packet WHERE stream_id IN (SELECT id FROM stream ${WHERE_CLAUSE});
DELETE FROM found_pattern WHERE packet_id IN (SELECT id FROM removed_id);
DELETE FROM packet WHERE id in (SELECT id FROM removed_id);
DELETE FROM stream_found_patterns WHERE stream_id IN (SELECT id FROM stream ${WHERE_CLAUSE});
DELETE FROM stream ${WHERE_CLAUSE};
"

date '+%H:%m:%S'


cd /root/packmate

echo "$COMMAND" | docker compose run --remove-orphans -T db psql -h localhost -p 65001 packmate packmate
