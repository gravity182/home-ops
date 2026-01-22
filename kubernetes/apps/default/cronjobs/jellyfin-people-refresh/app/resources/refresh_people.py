import json
import logging
import time
import tomllib
import urllib.parse
import urllib.request


def config_int(settings, key, default):
    value = settings.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer for settings.{key}: {value}")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer for settings.{key}: {value}")


def build_url(base_url, path, params):
    base = base_url.rstrip("/")
    url = f"{base}{path}"
    if params:
        return f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    return url


def get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} failed: status={response.status}")
        return json.load(response)


def post(url, timeout):
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Length", "0")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status


def has_primary_image(item):
    if item.get("PrimaryImageTag"):
        return True
    image_tags = item.get("ImageTags")
    if isinstance(image_tags, dict) and image_tags.get("Primary"):
        return True
    return False


def validate_config(cfg):
    if not cfg.get("targets"):
        raise ValueError("'targets' is required and must not be empty")
    for i, target in enumerate(cfg["targets"]):
        if "name" not in target:
            raise ValueError(f"targets[{i}]: 'name' is required")
        if "url" not in target:
            raise ValueError(f"targets[{i}]: 'url' is required")
        if "api_key_file" not in target:
            raise ValueError(f"targets[{i}]: 'api_key_file' is required")


def read_api_key(path):
    with open(path, "r", encoding="utf-8") as f:
        value = f.read().strip()
    if not value:
        raise ValueError(f"API key file is empty: {path}")
    return value


def process_target(logger, name, url, api_key, limit, page_sleep, item_sleep, timeout):
    start_index = 0
    total = None
    processed = 0
    queued = 0

    logger.info("Starting target: %s", name)

    while True:
        params = {
            "api_key": api_key,
            "includeItemTypes": "Person",
            "startIndex": start_index,
            "limit": limit,
            "enableImages": "true",
        }
        request_url = build_url(url, "/Items", params)
        data = get_json(request_url, timeout=timeout)
        items = data.get("Items") or []
        if total is None:
            total = data.get("TotalRecordCount")

        if not items:
            break

        for item in items:
            processed += 1
            item_id = item.get("Id")
            item_name = item.get("Name", "<unknown>")

            if not item_id:
                logger.warning(
                    "target=%s skipping item without Id: name=%s", name, item_name
                )
                continue

            if has_primary_image(item):
                continue

            refresh_params = {
                "api_key": api_key,
                "metadataRefreshMode": "FullRefresh",
                "imageRefreshMode": "FullRefresh",
                "replaceAllMetadata": "true",
                "replaceAllImages": "true",
            }
            refresh_url = build_url(
                url, f"/Items/{item_id}/Refresh", refresh_params
            )

            status = post(refresh_url, timeout=timeout)
            if status == 204:
                queued += 1
                logger.info(
                    "target=%s queued refresh: %s (%s)", name, item_name, item_id
                )
            else:
                logger.warning(
                    "target=%s refresh returned status %s: %s (%s)",
                    name,
                    status,
                    item_name,
                    item_id,
                )

            time.sleep(item_sleep)

        start_index += len(items)

        if total is not None and start_index >= total:
            break
        if len(items) < limit:
            break

        time.sleep(page_sleep)

    logger.info(
        "Finished target: %s processed=%s queued=%s total=%s",
        name,
        processed,
        queued,
        total,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("jellyfin-people-refresh")

    with open("/config/config.toml", "rb") as f:
        config = tomllib.load(f)

    validate_config(config)

    settings = config.get("settings", {})
    limit = config_int(settings, "limit", 50)
    page_sleep = config_int(settings, "page_sleep_seconds", 5)
    item_sleep = config_int(settings, "item_sleep_seconds", 1)
    timeout = config_int(settings, "http_timeout_seconds", 30)

    for target in config["targets"]:
        api_key = read_api_key(target["api_key_file"])
        process_target(
            logger=logger,
            name=target["name"],
            url=target["url"],
            api_key=api_key,
            limit=limit,
            page_sleep=page_sleep,
            item_sleep=item_sleep,
            timeout=timeout,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
