from ctypes import *
import re
import platform
import os

class OutputCoords(Structure):
    _fields_ = [
        ("lonL", c_double),
        ("lonR", c_double),
        ("latT", c_double),
        ("latB", c_double),
    ]

class ColorEntry(Structure):
    _fields_ = [
        ("value", c_double),
        ("red", c_ubyte),
        ("green", c_ubyte),
        ("blue", c_ubyte),
        ("alpha", c_ubyte),
        ("has2", c_bool),
        ("red2", c_ubyte),
        ("green2", c_ubyte),
        ("blue2", c_ubyte),
        ("alpha2", c_ubyte),
    ]

class ColorTable(Structure):
    _fields_ = [
        ("entries", POINTER(ColorEntry)),
        ("count", c_size_t),
        ("scale", c_double),
        ("offset", c_double),
    ]

    COMBINE_SPACES_REGEX = re.compile(r"  +")
    def __init__(self, filename = None):
        Structure.__init__(self)
        self.scale  = 1
        self.offset = 0
        self.step   = None
        self.rf     = (0, 0, 0, 0)

        if filename is None:
            values = [
                (75, 235, 235, 235, 255),
                (70, 153, 85, 201, 255),
                (65, 255, 0, 255, 255),
                (60, 192, 0, 0, 255),
                (55, 214, 0, 0, 255),
                (50, 255, 0, 0, 255),
                (45, 255, 144, 0, 255),
                (40, 231, 192, 0, 255),
                (35, 255, 255, 0, 255),
                (30, 0, 144, 0, 255),
                (25, 0, 200, 0, 255),
                (20, 0, 255, 0, 255),
                (15, 0, 0, 246, 255),
                (10, 1, 160, 246, 255),
                (5, 0, 236, 236, 255),
                (0, 187, 255, 255, 255),
                (-5, 174, 238, 238, 255),
                (-10, 150, 205, 205, 255),
                (-15, 102, 139, 139, 255),
                (-20, 50, 79, 79, 255),
            ]
        else:
            with open(filename) as file:
                values = []
                for i, line in enumerate(file.readlines()):
                    try:
                        commentless, _, comment = line.partition(";")
                        commentless = commentless.strip()
                        if len(commentless) < 1:
                            continue

                        name, _, value = commentless.partition(":")
                        value = value.strip()
                        if len(value) == 0:
                            raise Exception(f"Could not parse color table")

                        name = name.lower()
                        if name == "product":
                            continue
                        elif name == "units":
                            continue
                        elif name == "scale":
                            self.scale = float(value)
                        elif name == "offset":
                            self.offset = float(value)
                        elif name == "step":
                            self.step = float(value)
                        elif name == "rf":
                            self.rf = self._parse_color(value, "rf", False)
                        elif name == "color":
                            values.append(self._parse_color(value, "color", True))
                        elif name == "color4":
                            values.append(self._parse_color(value, "color4", True))
                        elif name == "solidcolor":
                            color = self._parse_color(value, "color", False)
                            values.append(color + color[1:])
                        elif name == "solidcolor4":
                            color = self._parse_color(value, "color4", False)
                            values.append(color + color[1:])
                        else:
                            raise Exception(f"Unknown name {repr(name)}")
                    except Exception as e:
                        e.add_note(f"in color table {repr(filename)}, line {i + 1}\n{line}")
                        raise e
        values = sorted(values, key = lambda a: a[0])

        self.entries_ = (ColorEntry * len(values))()
        for i, value in enumerate(values):
            self.entries_[i].value = c_double(value[0])
            self.entries_[i].red   = c_ubyte(value[1])
            self.entries_[i].green = c_ubyte(value[2])
            self.entries_[i].blue  = c_ubyte(value[3])
            self.entries_[i].alpha = c_ubyte(value[4])
            self.entries_[i].has2  = c_bool(len(value) > 5)
            if self.entries_[i].has2:
                self.entries_[i].red2   = c_ubyte(value[5])
                self.entries_[i].green2 = c_ubyte(value[6])
                self.entries_[i].blue2  = c_ubyte(value[7])
                self.entries_[i].alpha  = c_ubyte(value[8])

        self.entries = cast(self.entries_, POINTER(ColorEntry))
        self.count   = c_size_t(len(values))

    def _parse_color(self, text, colorType, optional):
        parts = self.COMBINE_SPACES_REGEX.sub(" ", text).split(" ")

        try:
            if colorType == "color4":
                if len(parts) == 5 or (optional and len(parts) == 8):
                    parts = [float(parts[0])] + [int(part) for part in parts[1:]]
                    return tuple(parts)
            elif colorType == "color":
                if len(parts) == 4:
                    parts = [float(parts[0])] + [int(part) for part in parts[1:]] + [255]
                    return tuple(parts)
                elif optional and len(parts) == 7:
                    parts = [float(parts[0])] + \
                            [int(part) for part in parts[1:4]] + [255] + \
                            [int(part) for part in parts[4:7]] + [255]
                    return tuple(parts)
            elif colorType == "rf":
                parts = [int(part) for part in parts]
                if len(parts) == 3:
                    return tuple(parts + [255])
                elif len(parts) == 4:
                    return tuple(parts)

        except Exception as e:
            raise Exception(f"Could not parse color {repr(text)}: {e}")

        raise Exception(f"Could not parse color {repr(text)}")


class Settings(Structure):
    _fields_ = [
        ("url", c_char_p),
        ("gzipped", c_bool),
        ("imageFile", c_char_p),
        ("palette", POINTER(ColorTable)),
        ("imageWidth", c_size_t),
        ("imageHeight", c_size_t),
        ("verbose", c_bool),
        ("timeout", c_ulonglong),
    ]

    def __init__(self, url, gzipped, imageFile, palette, imageWidth,
                 imageHeight, verbose, timeout):
        Structure.__init__(self)

        if isinstance(palette, ColorTable):
            self.palette_ = palette
        else:
            self.palette_ = ColorTable(palette)

        self.url         = c_char_p(url.encode("utf-8"))
        self.gzipped     = c_bool(gzipped)
        self.imageFile   = c_char_p(imageFile.encode("utf-8"))
        self.imageWidth  = c_size_t(imageWidth)
        self.imageHeight = c_size_t(imageHeight)
        self.palette     = pointer(self.palette_)
        self.verbose     = c_bool(verbose)
        self.timeout     = c_ulonglong(timeout)

class Grib2PfLib:
    PATHS = [
        "./libgrib2pf",
        "./build/libgrib2pf",
        "libgrib2pf",
    ]
    def __init__(self, path = None):
        if path is None:
            for p in self.PATHS:
                if platform.system() == "Linux":
                    p += ".so"
                path = p
                if os.path.exists(path):
                    break

        self.lib = cdll.LoadLibrary(path)

    def generate_image(self, settings):
        if not isinstance(settings, Settings):
            raise TypeError("settings should be of type Settings")

        output = OutputCoords()

        err = self.lib.generate_image(byref(settings), byref(output))
        return err, output.lonL, output.lonR, output.latT, output.latB

if __name__ == "__main__":
    c = ColorTable()
    settings = Settings("https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz",
                        True,
                        "/home/aden/test/test.png",
                        c, #"/home/aden/.config/supercell_wx/palettes/BR.pal",
                        1920,
                        1080,
                        True,
                        30)
    lib = Grib2PfLib()
    lib.generate_image(settings)

