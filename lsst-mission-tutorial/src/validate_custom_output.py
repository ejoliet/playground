from lsst.daf.butler import Butler


def main() -> None:
    butler = Butler("DATA_REPO")

    refs = list(
        butler.registry.queryDatasets(
            "myMissionCalexp",
            collections="my_mission/run1",
        )
    )

    print(f"Found {len(refs)} myMissionCalexp dataset(s).")

    for ref in refs:
        exposure = butler.get(ref)
        print("Data ID:", dict(ref.dataId))
        print("Dimensions:", exposure.getDimensions())


if __name__ == "__main__":
    main()
