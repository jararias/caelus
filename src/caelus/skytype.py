
import enum


class SkyType(enum.IntEnum):
    """
    Enumerate type for the sky type
    """

    UNKNOWN = 1
    OVERCAST = 2
    THICK_CLOUDS = 3
    SCATTER_CLOUDS = 4
    THIN_CLOUDS = 5
    CLOUDLESS = 6
    CLOUD_ENHANCEMENT = 7

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN

    @classmethod
    def skip_unknown(cls):
        """
        Iterate over the class members, but skip the UNKNOWN type
        """
        for sky_type in cls:
            if sky_type is cls.UNKNOWN:
                continue
            yield sky_type
