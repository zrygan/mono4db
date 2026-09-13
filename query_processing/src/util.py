from pathlib import Path
from shutil import rmtree


def clean_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.is_dir():
            rmtree(item)
        else:
            item.unlink()
