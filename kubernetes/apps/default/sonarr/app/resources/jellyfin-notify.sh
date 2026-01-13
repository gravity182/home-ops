#!/bin/bash
event_type="${sonarr_eventtype}${radarr_eventtype}"

if [ "$event_type" = "Test" ]; then
  echo "Test successful"
  exit 0
fi

curl -sX POST "${JELLYFIN_URL}/Items/${JELLYFIN_LIBRARY_ID}/Refresh?Recursive=true&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" > /dev/null

curl -sX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_REFRESH_PEOPLE_TASK_ID}?api_key=${JELLYFIN_API_KEY}" > /dev/null
