#!/bin/bash
event_type="${bazarr_eventtype}"

if [ "$event_type" = "Test" ]; then
  echo "Test successful"
  exit 0
fi

# Determine which library to refresh based on media type
if [ -n "${bazarr_sonarr_seriesid}" ] || [ -n "${sonarr_series_id}" ]; then
  # TV show - use TV library ID
  LIBRARY_ID="${JELLYFIN_TV_LIBRARY_ID}"
elif [ -n "${bazarr_radarr_movieid}" ] || [ -n "${radarr_movie_id}" ]; then
  # Movie - use Movie library ID
  LIBRARY_ID="${JELLYFIN_MOVIE_LIBRARY_ID}"
else
  echo "Unable to determine media type, skipping Jellyfin refresh"
  exit 1
fi

curl -sX POST "${JELLYFIN_URL}/Items/${LIBRARY_ID}/Refresh?Recursive=true&api_key=${JELLYFIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 0" > /dev/null
