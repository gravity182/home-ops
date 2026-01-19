#!/bin/bash
event_type="${radarr_eventtype}"

if [ "$event_type" = "Test" ]; then
  echo "Test successful"
  exit 0
fi

if [ -z "$JELLYFIN_PATH_FROM" ] || [ -z "$JELLYFIN_PATH_TO" ]; then
  echo "JELLYFIN_PATH_FROM and JELLYFIN_PATH_TO must be set"
  exit 1
fi

echo "event_type=${event_type:-unknown}"

source_path=""
if [ -n "$radarr_moviefile_path" ]; then
  source_path="$radarr_moviefile_path"
elif [ -n "$radarr_movie_path" ]; then
  source_path="$radarr_movie_path"
elif [ -n "$radarr_moviefile_paths" ]; then
  source_path="${radarr_moviefile_paths%%|*}"
fi

if [ -n "$source_path" ]; then
  echo "source_path=$source_path"
else
  echo "source_path is empty"
fi

jellyfin_path="${source_path/#$JELLYFIN_PATH_FROM/$JELLYFIN_PATH_TO}"

if [ -n "$jellyfin_path" ]; then
  echo "mapped_path=$jellyfin_path"
fi

curl -fsSX POST "${JELLYFIN_URL}/Items/${JELLYFIN_LIBRARY_ID}/Refresh?Recursive=true&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" || exit 1
sleep 5

if [ -n "$jellyfin_path" ]; then
  items_json="$(curl -fsS "${JELLYFIN_URL}/Items?parentId=${JELLYFIN_LIBRARY_ID}&recursive=true&includeItemTypes=Movie&fields=Path&api_key=${JELLYFIN_API_KEY}")" || exit 1
  item_id="$(jq -r --arg path "$jellyfin_path" '.Items[]? | select(.Path == $path) | .Id' <<<"$items_json" | head -n 1)"
  if [ -n "$item_id" ] && [ "$item_id" != "null" ]; then
    echo "item_id=$item_id"
    curl -fsSX POST "${JELLYFIN_URL}/Items/${item_id}/Refresh?metadataRefreshMode=FullRefresh&replaceAllMetadata=true&imageRefreshMode=None&replaceAllImages=false&api_key=${JELLYFIN_API_KEY}" \
      -H "Content-Length: 0" || exit 1
    echo "refresh metadata queued"
    sleep 5
  else
    echo "Jellyfin item not found for path: $jellyfin_path"
  fi
else
  echo "No Radarr path available; skipping per-item metadata refresh."
fi

curl -fsSX POST "${JELLYFIN_URL}/ScheduledTasks/Running/${JELLYFIN_REFRESH_PEOPLE_TASK_ID}?api_key=${JELLYFIN_API_KEY}" || exit 1

echo "movie imported successfully: $radarr_movie_title"
exit 0
