#!/bin/bash
set -euo pipefail

start_time="$(date +%s)"

if [ -n "${radarr_eventtype:-}" ]; then
  service="radarr"
  event_type="$radarr_eventtype"
  item_type="Movie"
  display_type="Movie"
  title="${radarr_movie_title:-}"
elif [ -n "${sonarr_eventtype:-}" ]; then
  service="sonarr"
  event_type="$sonarr_eventtype"
  item_type="Episode"
  display_type="TV Series"
  title="${sonarr_series_title:-}"
else
  echo "Could not detect service type (neither radarr_eventtype nor sonarr_eventtype is set)" >&2
  exit 1
fi

echo "service=${service} event_type=${event_type} title=${title}"

if [ "$event_type" = "Test" ]; then
  echo "Test event received, exiting"
  exit 0
fi

if [ -z "${JELLYFIN_URL:-}" ] || [ -z "${JELLYFIN_API_KEY:-}" ]; then
  echo "JELLYFIN_URL and JELLYFIN_API_KEY must be set" >&2
  exit 1
fi

if [ -z "${JELLYFIN_PATH_FROM:-}" ] || [ -z "${JELLYFIN_PATH_TO:-}" ]; then
  echo "JELLYFIN_PATH_FROM and JELLYFIN_PATH_TO must be set" >&2
  exit 1
fi

if [ -z "${JELLYFIN_LIBRARY_ID:-}" ]; then
  echo "JELLYFIN_LIBRARY_ID must be set" >&2
  exit 1
fi

for var in JELLYFIN_INTRO_SKIPPER_TASK_ID JELLYFIN_MEDIA_SEGMENT_SCAN_TASK_ID JELLYFIN_EXTRACT_CHAPTERS_TASK_ID JELLYFIN_GENERATE_TRICKPLAY_TASK_ID; do
  if [ -z "${!var:-}" ]; then
    echo "${var} must be set" >&2
    exit 1
  fi
done

echo "jellyfin_url=${JELLYFIN_URL} library_id=${JELLYFIN_LIBRARY_ID:-unset}"
echo "path_from=${JELLYFIN_PATH_FROM} path_to=${JELLYFIN_PATH_TO}"

jf_get() {
  local endpoint="$1"
  local response
  if ! response="$(curl -fsS -H "Authorization: MediaBrowser Token=\"${JELLYFIN_API_KEY}\"" "${JELLYFIN_URL}${endpoint}" 2>&1)"; then
    echo "GET ${endpoint} failed: ${response}" >&2
    return 1
  fi
  echo "$response"
}

jf_post() {
  local endpoint="$1"
  local response
  if ! response="$(curl -fsSX POST -H "Authorization: MediaBrowser Token=\"${JELLYFIN_API_KEY}\"" -H "Content-Length: 0" "${JELLYFIN_URL}${endpoint}" 2>&1)"; then
    echo "POST ${endpoint} failed: ${response}" >&2
    return 1
  fi
}

poll_for_item() {
  local path="$1" type="$2" timeout=120 interval=2 elapsed=0
  while [ $elapsed -lt $timeout ]; do
    local items_json
    items_json="$(jf_get "/Items?parentId=${JELLYFIN_LIBRARY_ID}&recursive=true&includeItemTypes=${type}&fields=Path")" || {
      sleep "$interval"
      elapsed=$((elapsed + interval))
      continue
    }
    local id
    id="$(jq -r --arg path "$path" '[.Items[]? | select(.Path == $path) | .Id][0] // empty' <<<"$items_json")"
    if [ -n "$id" ] && [ "$id" != "null" ]; then
      echo "$id"
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  return 1
}

check_items_metadata() {
  local check_ids="$1" check_count="$2" refresh_id="$3"

  local items_json
  items_json="$(jf_get "/Items?ids=${check_ids}&fields=Overview")" || return 1

  local returned
  returned="$(jq -r '.Items | length' <<<"$items_json")"
  if [ "$returned" != "$check_count" ]; then
    echo "${returned}/${check_count} items returned (expected ${check_count})" >&2
    return 1
  fi

  # Check: Name must not contain provider ID tags, Overview must be non-empty
  local bad_items
  bad_items="$(jq -r '[.Items[] | select(
    (.Name | test("\\[(tmdb|imdb|tvdb)")) or
    ((.Overview // "") == "")
  )] | length' <<<"$items_json")"
  if [ "$bad_items" != "0" ]; then
    echo "${bad_items}/${check_count} items missing metadata" >&2
    return 1
  fi

  # For sonarr: check that no unknown season exists under the series
  if [ "$service" = "sonarr" ]; then
    local seasons_json
    seasons_json="$(jf_get "/Items?parentId=${refresh_id}&includeItemTypes=Season")" || return 1
    local unknown
    unknown="$(jq -r '[.Items[] | select(.IndexNumber == null)] | length' <<<"$seasons_json")"
    if [ "$unknown" != "0" ]; then
      echo "${unknown} unknown season(s) found" >&2
      return 1
    fi
  fi

  return 0
}

poll_items_metadata() {
  local refresh_id="$1" check_ids="$2" check_count="$3"
  local max_attempts=2 attempt=0

  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))

    jf_post "/Items/${refresh_id}/Refresh?metadataRefreshMode=FullRefresh&replaceAllMetadata=true&imageRefreshMode=FullRefresh&replaceAllImages=false&regenerateTrickplay=false" || return 1
    echo "Metadata refresh queued (attempt ${attempt}/${max_attempts})"

    local timeout=15 interval=3 elapsed=0
    while [ $elapsed -lt $timeout ]; do
      sleep "$interval"
      elapsed=$((elapsed + interval))
      local status
      if status="$(check_items_metadata "$check_ids" "$check_count" "$refresh_id" 2>&1)"; then
        echo "All metadata complete after ${elapsed}s (attempt ${attempt})"
        return 0
      fi
      echo "Waiting for metadata: ${status} (${elapsed}s, attempt ${attempt})"
    done
    echo "Metadata incomplete after ${timeout}s (attempt ${attempt})" >&2
  done
  echo "Metadata may be incomplete after ${max_attempts} attempts, proceeding anyway" >&2
  return 0
}

wait_for_task() {
  local task_id="$1" label="$2" timeout=300 interval=3 elapsed=0
  echo "Starting task '${label}' (id=${task_id})"
  sleep 1
  while [ $elapsed -lt $timeout ]; do
    local task_json
    task_json="$(jf_get "/ScheduledTasks/${task_id}")" || { sleep "$interval"; elapsed=$((elapsed + interval)); continue; }
    local state
    state="$(jq -r '.State' <<<"$task_json")"
    if [ "$state" = "Idle" ]; then
      echo "Task '${label}' completed after ${elapsed}s"
      return 0
    fi
    local progress
    progress="$(jq -r '.CurrentProgressPercentage // "?"' <<<"$task_json")"
    echo "Task '${label}': state=${state} progress=${progress}% (${elapsed}s)"
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  echo "Task '${label}' did not complete within ${timeout}s" >&2
  return 1
}

echo "Refreshing library (id=${JELLYFIN_LIBRARY_ID})"
jf_post "/Items/${JELLYFIN_LIBRARY_ID}/Refresh" || exit 1

if [ "$event_type" != "Download" ]; then
  echo "Not a Download event; library refresh only"
  exit 0
fi

source_paths=""
if [ "$service" = "radarr" ]; then
  if [ -n "${radarr_moviefile_path:-}" ]; then
    source_paths="$radarr_moviefile_path"
  elif [ -n "${radarr_movie_path:-}" ]; then
    source_paths="$radarr_movie_path"
  elif [ -n "${radarr_moviefile_paths:-}" ]; then
    source_paths="$radarr_moviefile_paths"
  fi
elif [ "$service" = "sonarr" ]; then
  if [ -n "${sonarr_episodefile_paths:-}" ]; then
    source_paths="$sonarr_episodefile_paths"
  elif [ -n "${sonarr_episodefile_path:-}" ]; then
    source_paths="$sonarr_episodefile_path"
  fi
fi

if [ -z "$source_paths" ]; then
  echo "No source paths found in environment variables" >&2
  exit 1
fi

IFS='|' read -ra paths <<< "$source_paths"
folder="$(dirname "${paths[0]}")"
folder="${folder/#$JELLYFIN_PATH_FROM/$JELLYFIN_PATH_TO}"
echo "Processing ${#paths[@]} file(s) in ${folder}"

# Poll for all items to appear in Jellyfin
item_ids=()
for source_path in "${paths[@]}"; do
  jellyfin_path="${source_path/#$JELLYFIN_PATH_FROM/$JELLYFIN_PATH_TO}"

  item_id="$(poll_for_item "$jellyfin_path" "$item_type")" || { echo "Item not found: $jellyfin_path" >&2; exit 1; }
  item_ids+=("$item_id")
done

# For sonarr, refresh the Series item (cascades to all episodes)
# For radarr, refresh the Movie item directly
if [ "$service" = "sonarr" ]; then
  if [ -z "${sonarr_series_path:-}" ]; then
    echo "sonarr_series_path is empty" >&2
    exit 1
  fi
  series_jf_path="${sonarr_series_path/#$JELLYFIN_PATH_FROM/$JELLYFIN_PATH_TO}"
  refresh_id="$(poll_for_item "$series_jf_path" "Series")" || { echo "Series not found: $series_jf_path" >&2; exit 1; }
  echo "series_id=${refresh_id}"
else
  refresh_id="${item_ids[0]}"
fi

ids_csv="$(IFS=','; echo "${item_ids[*]}")"
poll_items_metadata "$refresh_id" "$ids_csv" "${#item_ids[@]}" || exit 1

jf_post "/ScheduledTasks/Running/${JELLYFIN_INTRO_SKIPPER_TASK_ID}" || exit 1
wait_for_task "$JELLYFIN_INTRO_SKIPPER_TASK_ID" "intro skipper" || exit 1

jf_post "/ScheduledTasks/Running/${JELLYFIN_MEDIA_SEGMENT_SCAN_TASK_ID}" || exit 1
wait_for_task "$JELLYFIN_MEDIA_SEGMENT_SCAN_TASK_ID" "media segment scan" || exit 1

# Fire-and-forget: these tasks are long-running and non-critical, so we trigger them without waiting
jf_post "/ScheduledTasks/Running/${JELLYFIN_EXTRACT_CHAPTERS_TASK_ID}" || exit 1
jf_post "/ScheduledTasks/Running/${JELLYFIN_GENERATE_TRICKPLAY_TASK_ID}" || exit 1
echo "Triggered background tasks: extract chapters, generate trickplay"

elapsed=$(($(date +%s) - start_time))
echo "${display_type} imported successfully: ${title} (total time: ${elapsed}s)"
exit 0
