import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
import lsst.pipe.base.connectionTypes as cT


class SimpleCalibrationConnections(
    pipeBase.PipelineTaskConnections,
    dimensions=("instrument", "visit", "detector"),
):
    input_exposure = cT.Input(
        name="calexp",
        doc="Input calibrated exposure used as a stand-in for a mission image.",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )

    output_exposure = cT.Output(
        name="myMissionCalexp",
        doc="Mission-specific calibrated exposure produced by the tutorial task.",
        storageClass="ExposureF",
        dimensions=("instrument", "visit", "detector"),
    )


class SimpleCalibrationConfig(
    pipeBase.PipelineTaskConfig,
    pipelineConnections=SimpleCalibrationConnections,
):
    bias_level = pexConfig.Field(
        dtype=float,
        default=0.0,
        doc="Scalar bias level to subtract from image pixels.",
    )

    flat_scale = pexConfig.Field(
        dtype=float,
        default=1.0,
        doc="Scalar flat-field scale to divide image pixels by.",
    )


class SimpleCalibrationTask(pipeBase.PipelineTask):
    """Minimal mission-specific calibration driver.

    This task demonstrates the LSST/Rubin extension pattern:
    read an ExposureF from Butler, apply configurable mission logic,
    and write a new ExposureF dataset.
    """

    ConfigClass = SimpleCalibrationConfig
    _DefaultName = "simpleCalibration"

    def run(self, input_exposure):
        if self.config.flat_scale == 0.0:
            raise ValueError("flat_scale must be non-zero")

        output = input_exposure.clone()
        masked_image = output.getMaskedImage()

        masked_image -= self.config.bias_level
        masked_image /= self.config.flat_scale

        return pipeBase.Struct(output_exposure=output)
