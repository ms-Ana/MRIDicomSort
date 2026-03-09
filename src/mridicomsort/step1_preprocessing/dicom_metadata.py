CONTRAST_METADATA = [
    "ContrastBolusAgent",
    "ContrastBolusRoute",
    "ContrastBolusVolume",
    "ContrastBolusTotalDose",
    "ContrastBolusIngredient",
    "ContrastBolusIngredientConcentration",
]  # contrast parameters

IDENTIFICATION_METADATA = [
    "ImageType",
    "SOPClassUID",
    "Modality",
    "StudyDescription",
    "SeriesDescription",
]  # TOP LEVEL parameters to help LLM to define modality and type of scan


ACQUISITION_METADATA = [
    "ScanningSequence",
    "SequenceVariant",
    "ScanOptions",
    "MRAcquisitionType",
    "SequenceName",
    "AngioFlag",
    "SliceThickness",
    "RepetitionTime",
    "EchoTime",
    "InversionTime",
    "NumberOfAverages",
    "ImagingFrequency",
    "ImagedNucleus",
    "EchoNumbers",
    "MagneticFieldStrength",
    "SpacingBetweenSlices",
    "NumberOfPhaseEncodingSteps",
    "EchoTrainLength",
    "PixelBandwidth",
    "ReconstructionDiameter",
    "FlipAngle",
    "VariableFlipAngleFlag",
    "DiffusionBValue",
]  # physically meaningful parameters that can be used for grouping and are not related to the image presentation


RELATIONSHIP_METADATA = ["SeriesNumber", "AcquisitionNumber"]
METADATA = [
    *CONTRAST_METADATA,
    *ACQUISITION_METADATA,
    *IDENTIFICATION_METADATA,
    *RELATIONSHIP_METADATA,
]
