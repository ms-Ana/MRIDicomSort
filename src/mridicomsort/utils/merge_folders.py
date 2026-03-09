"""Merge contents of two directories, handling identical and differing files appropriately."""

import os
import shutil
import filecmp
from pathlib import Path
import click
from tqdm import tqdm


def merge_dirs(src: Path, dst: Path, overwrite: bool = True):
    src = Path(src)
    dst = Path(dst)
    for root, dirs, files in tqdm(
        os.walk(src, topdown=False), desc="Merging directories"
    ):
        rel_root = Path(root).relative_to(src)
        dst_root = dst / rel_root
        dst_root.mkdir(parents=True, exist_ok=True)

        for f in files:
            src_file = Path(root) / f
            dst_file = dst_root / f

            if dst_file.exists():
                if filecmp.cmp(src_file, dst_file, shallow=False):
                    # identical → delete source
                    src_file.unlink()
                else:
                    if overwrite:
                        shutil.move(str(src_file), str(dst_file))
                    else:
                        # rename to avoid overwrite
                        new_dst = dst_file.with_name(
                            dst_file.stem + "_src" + dst_file.suffix
                        )
                        print(
                            f"File {dst_file} exists and differs. Moving source to {new_dst}"
                        )
                        shutil.move(str(src_file), str(new_dst))
            else:
                print(f"Moving {src_file} to {dst_file}")
                shutil.move(str(src_file), str(dst_file))

        # clean up empty dirs
        try:
            Path(root).rmdir()
        except OSError:
            pass


@click.command()
@click.argument("src", type=click.Path(exists=True, file_okay=False))
@click.argument("dst", type=click.Path(file_okay=False))
@click.option("--no-overwrite", is_flag=True, help="Do not overwrite existing files")
def cli(src, dst, no_overwrite):
    merge_dirs(src, dst, overwrite=not no_overwrite)


if __name__ == "__main__":
    cli()
