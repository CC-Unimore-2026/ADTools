#!/bin/bash

set -e

list_of_containers=`docker ps -a --format "{{.Names}}"`
containers=`docker ps -f status=running --format "{{.Names}}"`

IFS=$'\n'
for container in $list_of_containers
do
  if echo $containers | grep -q $container; then  
    echo "$container online"
  else
    echo "$container offline"
    curl $1 -X POST -H "Content-Type: application/json" -d "{\"content\":\"CONTAINER ${container} IS DOWN!!!!! <@&944196602967502869>\"}" # &> /dev/null
  fi
done
exit 0