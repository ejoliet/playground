import numpy as np
from lsst.daf.butler import Butler


def main() -> None:
    butler = Butler("DATA_REPO")

    refs = list(
        butler.registry.queryDatasets(
            "calexp",
            collections="demo_collection",
        )
    )

    if not refs:
        raise RuntimeError("No calexp datasets found in demo_collection.")

    ref = refs[0]
    exposure = butler.get(ref)

    image = exposure.getImage().array

    print("Data ID:", dict(ref.dataId))
    print("Image shape:", image.shape)
    print("Mean:", float(np.nanmean(image)))
    print("Std:", float(np.nanstd(image)))
    print("Min:", float(np.nanmin(image)))
    print("Max:", float(np.nanmax(image)))


if __name__ == "__main__":
    main()
