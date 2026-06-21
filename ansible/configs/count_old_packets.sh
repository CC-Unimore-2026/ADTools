#!/bin/bash

OLD_MINUTES=30
START_MS_TS="$(($(date +%s%N)/1000000 - ${OLD_MINUTES}*60*1000))"

WHERE_CLAUSE="WHERE stream.favorite != true AND stream.end_timestamp < ${START_MS_TS}"

CMD="CREATE TEMP TABLE removed_id AS SELECT id FROM packet WHERE stream_id IN (SELECT id FROM stream ${WHERE_CLAUSE}); SELECT COUNT(*) FROM removed_id"

echo "$CMD" | docker compose run --remove-orphans -T db psql -h localhost -p 65001 packmate packmate
