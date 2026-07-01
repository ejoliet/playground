from lsst.daf.butler import Butler


def main() -> None:
    repo = "DATA_REPO"
    collection = "demo_collection"

    butler = Butler(repo)

    print("Collections:")
    for name in butler.registry.queryCollections():
        print(f"  - {name}")

    print("\nDataset types:")
    for dataset_type in butler.registry.queryDatasetTypes():
        print(f"  - {dataset_type.name}")

    print("\ncalexp datasets:")
    refs = list(
        butler.registry.queryDatasets(
            "calexp",
            collections=collection,
        )
    )

    for ref in refs:
        print(f"  - dataId={dict(ref.dataId)} run={ref.run}")

    print(f"\nFound {len(refs)} calexp dataset(s).")


if __name__ == "__main__":
    main()
