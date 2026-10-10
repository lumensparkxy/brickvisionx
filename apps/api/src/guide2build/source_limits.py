"""Environment-configurable source budgets; page/process safety ceilings stay fixed."""
import os


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.environ.get(name, default))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


MAX_BYTES = _integer("GUIDE2BUILD_PDF_MAX_MIB", 256, 1, 512) * 1024 * 1024
MAX_PAGES = _integer("GUIDE2BUILD_PDF_MAX_PAGES", 1000, 1, 2000)
DOWNLOAD_SECONDS = _integer("GUIDE2BUILD_PDF_DOWNLOAD_SECONDS", 300, 1, 900)
BATCH_PAGES = _integer("GUIDE2BUILD_RENDER_BATCH_PAGES", 25, 1, 25)
MAX_OUTPUT_BYTES = _integer("GUIDE2BUILD_RENDER_MAX_MIB", 2048, 1, 8192) * 1024 * 1024
FREE_RESERVE_BYTES = 256 * 1024 * 1024
PAGE_PIXELS = 24_000_000
BATCH_PIXELS = 150_000_000
CHILD_SECONDS = 90
CHILD_CPU_SECONDS = 60
CHILD_MEMORY_BYTES = 1536 * 1024 * 1024
PAGE_FILE_BYTES = 128 * 1024 * 1024
