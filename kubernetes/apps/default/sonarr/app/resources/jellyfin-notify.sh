#!/bin/bash
event_type="$${sonarr_eventtype}$${radarr_eventtype}"

if [ "$event_type" = "Test" ]; then
  echo "Test successful"
  exit 0
fi

curl -sX POST "http://jellyfin:8096/Items/$${JELLYFIN_LIBRARY_ID}/Refresh?Recursive=true&api_key=$${JELLYFIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" > /dev/null
