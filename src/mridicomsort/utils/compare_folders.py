import hashlib
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from pathlib import Path

import click
from tqdm import tqdm


def file_checksum(path, algo="blake2b", chunk_size=128 * 1024):
    """Computes a fast blake2b checksum."""
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def hash_worker(file_info, algo):
    """Worker: file_info is a tuple of (absolute_path, relative_path)"""
    abs_p, rel_p = file_info
    checksum = file_checksum(abs_p, algo)
    return checksum, rel_p


def get_dir_stats(dir_path):
    """Quick scan to get file sizes and paths."""
    path_obj = Path(dir_path)
    stats = []
    for p in tqdm(path_obj.rglob("*"), desc="Scanning files"):
        if p.is_file():
            try:
                stats.append(
                    {
                        "abs": p,
                        "rel": str(p.relative_to(path_obj)),
                        "size": p.stat().st_size,
                    }
                )
            except OSError:
                continue
    return stats


def process_directory(dir_stats, algo):
    """Processes hashes only for files where size-matching is required."""
    inventory = defaultdict(list)

    with ProcessPoolExecutor() as executor:
        worker_func = partial(hash_worker, algo=algo)
        tasks = [(f["abs"], f["rel"]) for f in dir_stats]

        futures = [executor.submit(worker_func, t) for t in tasks]
        for future in tqdm(as_completed(futures), total=len(tasks), desc="Hashing"):
            res = future.result()
            if res:
                checksum, rel_path = res
                inventory[checksum].append(rel_path)
    return inventory


@click.command()
@click.argument("dir1", type=click.Path(exists=True, file_okay=False))
@click.argument("dir2", type=click.Path(exists=True, file_okay=False))
@click.option("--output", default="comparison_result.json")
@click.option("--algo", default="blake2b", help="Fast hash: blake2b, md5, etc.")
def cli(dir1, dir2, algo, output):
    """Compare directories with high-speed hashing and parallel execution."""

    click.echo("Scanning metadata...")
    stats1 = get_dir_stats(dir1)
    stats2 = get_dir_stats(dir2)

    click.echo(f"Processing {dir1}...")
    c1 = process_directory(stats1, algo)

    click.echo(f"Processing {dir2}...")
    c2 = process_directory(stats2, algo)

    h1, h2 = set(c1.keys()), set(c2.keys())

    result = {
        "missing_from_dir2": {h: c1[h] for h in (h1 - h2)},
        "missing_from_dir1": {h: c2[h] for h in (h2 - h1)},
        "matched": {h: {"dir1": c1[h], "dir2": c2[h]} for h in (h1 & h2)},
    }

    with open(output, "w") as f:
        json.dump(result, f, indent=2)

    click.echo(f"\nDone! Matches: {len(result['matched'])} | Saved to {output}")


if __name__ == "__main__":
    cli()
