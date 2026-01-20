import fnmatch
import logging
import os
import shutil
import time
import tomllib

with open('/config/config.toml', 'rb') as f:
    config = tomllib.load(f)


def validate_config(cfg):
    if not cfg.get('paths'):
        raise ValueError("'paths' is required and must not be empty")
    if not cfg.get('metadata_patterns'):
        raise ValueError("'metadata_patterns' is required and must not be empty")
    for i, path in enumerate(cfg['paths']):
        if 'mount_path' not in path:
            raise ValueError(f"paths[{i}]: 'mount_path' is required")
        if 'max_depth' not in path:
            raise ValueError(f"paths[{i}]: 'max_depth' is required")
        if path['max_depth'] < 0:
            raise ValueError(f"paths[{i}]: 'max_depth' must be >= 0")


validate_config(config)

media_dirs = config['paths']
metadata_patterns = config['metadata_patterns']
dry_run = config.get('dry_run', True)

log_level = getattr(logging, config.get('log_level', 'info').upper(), logging.INFO)
dry_run_prefix = "[DRY RUN] " if dry_run else ""
logging.basicConfig(
    level=log_level,
    format=f'%(asctime)s - %(levelname)s - {dry_run_prefix}%(message)s'
)


def is_metadata_file(filename):
    """Check if a file matches any of the metadata patterns"""
    return any(fnmatch.fnmatch(filename.lower(), pattern.lower())
               for pattern in metadata_patterns)


def get_all_files(path):
    """Get all files recursively from a directory"""
    all_files = []
    for root, _, files in os.walk(path):
        for file in files:
            all_files.append(os.path.join(root, file))
    return all_files


def check_dir(path):
    """Check all files in the directory tree and remove it if all are metadata"""
    logging.debug(f"Checking directory: {path}")

    all_files = get_all_files(path)
    if not all_files:
        logging.info(f"Removing '{path}', reason=empty_directory, metadata_files=[]")
        if not dry_run:
            shutil.rmtree(path)
        return

    metadata_files = [f for f in all_files if is_metadata_file(os.path.basename(f))]
    if len(metadata_files) == len(all_files):
        metadata_files_relative = [os.path.relpath(f, path) for f in metadata_files]
        logging.info(f"Removing '{path}', reason=metadata_only, metadata_files={metadata_files_relative}")
        if not dry_run:
            shutil.rmtree(path)


def get_subdirs_at_depth(root_path, target_depth):
    """Get all directories up to the target depth level in reverse order (deepest first)"""
    if target_depth == 0:
        return [root_path]

    dirs_by_depth = {}

    for dirpath, dirnames, _ in os.walk(root_path):
        current_depth = dirpath[len(root_path):].count(os.sep)
        if current_depth <= target_depth - 1:
            full_paths = [os.path.join(dirpath, dirname) for dirname in dirnames]
            if current_depth + 1 not in dirs_by_depth:
                dirs_by_depth[current_depth + 1] = []
            dirs_by_depth[current_depth + 1].extend(full_paths)

    result = []
    for depth in range(target_depth, 0, -1):
        if depth in dirs_by_depth:
            result.extend(dirs_by_depth[depth])

    return result


def scan_root_dirs(media_dirs_config):
    """Check directories at their specified depth levels"""
    for dir_config in media_dirs_config:
        root_path = dir_config['mount_path']
        max_depth = dir_config['max_depth']

        if not os.path.exists(root_path):
            logging.warning(f"Skipping non-existent path: {root_path}")
            continue

        logging.info(f"Scanning {root_path} (max_depth={max_depth})")
        dirs_to_check = get_subdirs_at_depth(root_path, max_depth)
        for dir_path in dirs_to_check:
            if os.path.exists(dir_path):
                check_dir(dir_path)


if __name__ == '__main__':
    logging.debug("Starting media directory cleanup%s", " [DRY RUN]" if dry_run else "")
    logging.debug("Paths: %s", [d['mount_path'] for d in media_dirs])
    logging.debug("Metadata patterns: %s", metadata_patterns)

    start_time = time.time()
    scan_root_dirs(media_dirs)

    logging.debug("Finished in %.2f seconds", time.time() - start_time)
