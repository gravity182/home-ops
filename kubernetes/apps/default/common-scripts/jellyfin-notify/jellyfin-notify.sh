#!/bin/bash

if [ -n "$radarr_eventtype" ]; then
  service="radarr"
  event_type="$radarr_eventtype"
  item_type="Movie"
  display_type="Movie"
  title="$radarr_movie_title"
elif [ -n "$sonarr_eventtype" ]; then
  service="sonarr"
  event_type="$sonarr_eventtype"
  item_type="Series"
  display_type="TV Series"
  title="$sonarr_series_title"
else
  echo "Error: Could not detect service type"
  exit 1
fi

if [ "$event_type" = "Test" ]; then
  echo "Test successful"
  exit 0
fi

if [ -z "$JELLYFIN_PATH_FROM" ] || [ -z "$JELLYFIN_PATH_TO" ]; then
  echo "JELLYFIN_PATH_FROM and JELLYFIN_PATH_TO must be set"
  exit 1
fi

echo "service=$service"
echo "event_type=${event_type:-unknown}"

curl -fsSX POST "${JELLYFIN_URL}/Items/${JELLYFIN_LIBRARY_ID}/Refresh?Recursive=true&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" || exit 1

if [ "$event_type" != "Download" ]; then
  echo "Not a Download event; library refresh only"
  exit 0
fi

source_path=""
if [ "$service" = "radarr" ]; then
  if [ -n "$radarr_moviefile_path" ]; then
    source_path="$radarr_moviefile_path"
  elif [ -n "$radarr_movie_path" ]; then
    source_path="$radarr_movie_path"
  elif [ -n "$radarr_moviefile_paths" ]; then
    source_path="${radarr_moviefile_paths%%|*}"
  fi
elif [ "$service" = "sonarr" ]; then
  if [ -n "$sonarr_series_path" ]; then
    source_path="$sonarr_series_path"
  fi
fi

if [ -z "$source_path" ]; then
  echo "source_path is empty"
  exit 1
fi

echo "source_path=$source_path"

jellyfin_path="${source_path/#$JELLYFIN_PATH_FROM/$JELLYFIN_PATH_TO}"
echo "mapped_path=$jellyfin_path"

sleep 10

items_json="$(curl -fsS "${JELLYFIN_URL}/Items?parentId=${JELLYFIN_LIBRARY_ID}&recursive=true&includeItemTypes=${item_type}&fields=Path&api_key=${JELLYFIN_API_KEY}")" || exit 1
item_id="$(jq -r --arg path "$jellyfin_path" '.Items[]? | select(.Path == $path) | .Id' <<<"$items_json" | head -n 1)"

if [ -z "$item_id" ] || [ "$item_id" = "null" ]; then
  echo "Jellyfin item not found for path: $jellyfin_path"
  exit 1
fi

echo "item_id=$item_id"

# one call rarely works correctly, so make multiple calls with delays
curl -fsSX POST "${JELLYFIN_URL}/Items/${item_id}/Refresh?metadataRefreshMode=FullRefresh&replaceAllMetadata=false&imageRefreshMode=FullRefresh&replaceAllImages=false&regenerateTrickplay=false&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Length: 0" || exit 1
echo "refresh metadata queued"
sleep 30
curl -fsSX POST "${JELLYFIN_URL}/Items/${item_id}/Refresh?metadataRefreshMode=FullRefresh&replaceAllMetadata=true&imageRefreshMode=FullRefresh&replaceAllImages=false&regenerateTrickplay=false&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Length: 0" || exit 1
echo "refresh metadata queued"
sleep 30

curl -fsSX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_INTRO_SKIPPER_TASK_ID}?api_key=${JELLYFIN_API_KEY}" || exit 1
sleep 15
curl -fsSX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_MEDIA_SEGMENT_SCAN_TASK_ID}?api_key=${JELLYFIN_API_KEY}" || exit 1
sleep 5

curl -fsSX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_EXTRACT_CHAPTERS_TASK_ID}?api_key=${JELLYFIN_API_KEY}" || exit 1
curl -fsSX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_GENERATE_TRICKPLAY_TASK_ID}?api_key=${JELLYFIN_API_KEY}" || exit 1

echo "${display_type} imported successfully: $title"
exit 0
