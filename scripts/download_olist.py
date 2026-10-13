"""Download the Olist dataset from Kaggle into data/raw/olist/."""

import os
import shutil
from pathlib import Path

import kagglehub

DATASET = "olistbr/brazilian-ecommerce"
RAW_DIR = Path("data/raw/olist")
EXPECTED_FILES = (
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
)


def has_kaggle_credentials() -> bool:
    """Return True if Kaggle credentials are available (env vars or ~/.kaggle/kaggle.json)."""
    if os.environ.get("KAGGLE_API_TOKEN"):
        return True
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return True
    return (Path.home() / ".kaggle" / "kaggle.json").exists()


def download_olist(dest: Path = RAW_DIR) -> list[Path]:
    """Download the Olist CSVs into dest and return their paths. Skips if already present."""
    targets = [dest / name for name in EXPECTED_FILES]
    if all(target.exists() for target in targets):
        print(f"Olist already present in {dest}, skipping download.")
        return targets

    if not has_kaggle_credentials():
        raise SystemExit(
            "No Kaggle credentials found. Set KAGGLE_API_TOKEN in .env (see .env.example)."
        )

    try:
        cache_dir = Path(kagglehub.dataset_download(DATASET))
    except Exception as exc:
        raise SystemExit(f"Kaggle download failed: {exc}") from exc

    dest.mkdir(parents=True, exist_ok=True)
    for target in targets:
        source = next(cache_dir.rglob(target.name), None)
        if source is None:
            raise SystemExit(f"File missing from the Kaggle download: {target.name}")
        shutil.copy2(source, target)

    print(f"Copied {len(targets)} files to {dest}")
    return targets


def main() -> None:
    download_olist()


if __name__ == "__main__":
    main()
