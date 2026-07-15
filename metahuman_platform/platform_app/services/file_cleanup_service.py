from pathlib import Path


class FileCleanupService:
    def remove_paths(self, paths: list[str | None]):
        for path in paths:
            if not path:
                continue
            target = Path(path)
            if target.exists() and target.is_file():
                target.unlink()
                continue
            if target.exists() and target.is_dir():
                for child in sorted(target.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                target.rmdir()
