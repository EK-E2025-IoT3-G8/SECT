#!/bin/bash
dump_file="$(date +%Y%m%d_%H%M%S).psql"
pg_dump -U postgres -d hospital > "$dump_file" && scp "$dump_file" device:/home/sensor/ && rm "$dump_file"