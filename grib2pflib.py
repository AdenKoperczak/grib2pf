from ctypes import *
import re
import os
import sys
from enum import IntEnum

class ImageArea(Structure):
    _fields_ = [
        ("lonL", c_double),
        ("lonR", c_double),
        ("latT", c_double),
        ("latB", c_double),
    ]

class OutputImageAreas(Structure):
    _fields_ = [
        ("topLeftArea",     ImageArea),
        ("topRightArea",    ImageArea),
        ("bottomLeftArea",  ImageArea),
        ("bottomRightArea", ImageArea),
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

    def __str__(self):
        if self.has2:
            return f"{self.value:>5} {self.red:>3} {self.green:>3} {self.blue:>3} {self.alpha:>3} {self.red2:>3} {self.green2:>3} {self.blue2:>3} {self.alpha2:>3}"
        else:
            return f"{self.value:>5} {self.red:>3} {self.green:>3} {self.blue:>3} {self.alpha:>3}"

class ColorTable(Structure):
    _fields_ = [
        ("entries", POINTER(ColorEntry)),
        ("count", c_size_t),
        ("scale", c_double),
        ("offset", c_double),
    ]

    COMBINE_SPACES_REGEX = re.compile(r"  +")
    def __init__(self, filename = None, extraLogs = False):
        Structure.__init__(self)
        self.scale  = c_double(1)
        self.offset = c_double(0)
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
                            print("Could not parse color table")
                            continue

                        name = name.lower()
                        if name == "product":
                            if extraLogs:
                                print(name, value)
                        elif name == "units":
                            if extraLogs:
                                print(name, value)
                        elif name == "decimals":
                            if extraLogs:
                                print(name, value)
                        elif name == "scale":
                            self.scale = c_double(float(value))
                        elif name == "offset":
                            self.offset = c_double(float(value))
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
                            print(f"Unknown name {repr(name)}")
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
                self.entries_[i].alpha2 = c_ubyte(value[8])

        self.entries = cast(self.entries_, POINTER(ColorEntry))
        self.count   = c_size_t(len(values))

        if (extraLogs):
            print(self)

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

    def __str__(self):
        return "\n".join(str(entrie) for entrie in self.entries[0:self.count])

RenderModes = {
    "Average_Data": 0,
    "Nearest_Data": 1,
    "Nearest_Fast_Data": 2,
    "Max_Data": 3,
    "Min_Data": 4,
}

class MessageSettings(Structure):
    _fields_ = [
        ("tiled", c_bool),
        ("topLeftImageFile",     c_char_p),
        ("topRightImageFile",    c_char_p),
        ("bottomLeftImageFile",  c_char_p),
        ("bottomRightImageFile", c_char_p),

        ("palette", POINTER(ColorTable)),
        ("imageWidth", c_size_t),
        ("imageHeight", c_size_t),
        ("title", c_char_p),
        ("mode", c_int),
        ("minimum", c_double),

        ("customArea", c_bool),
        ("area", ImageArea),

        ("offset", c_size_t),

        ("output", OutputImageAreas),
    ]

    def set(self, imageFiles, palette, imageWidth, imageHeight, title,
                 mode, offset, minimum, area = None):

        if isinstance(mode, str):
            mode = RenderModes[mode]

        if isinstance(palette, ColorTable):
            self.palette_ = palette
        else:
            self.palette_ = ColorTable(palette)

        if isinstance(imageFiles, str):
            self.tiled = c_bool(False)
            self.topLeftImageFile = c_char_p(imageFiles.encode("utf-8"))
        elif len(imageFiles) == 1:
            self.tiled = c_bool(False)
            self.topLeftImageFile = c_char_p(imageFiles[0].encode("utf-8"))
        elif len(imageFiles) == 4:
            self.tiled = c_bool(True)
            self.topLeftImageFile = c_char_p(imageFiles[0].encode("utf-8"))
            self.topRightImageFile = c_char_p(imageFiles[1].encode("utf-8"))
            self.bottomLeftImageFile = c_char_p(imageFiles[2].encode("utf-8"))
            self.bottomRightImageFile = c_char_p(imageFiles[3].encode("utf-8"))
        else:
            raise ValueError("imageFiles must be a string list with 1 item, or list with 4 items")

        self.palette     = pointer(self.palette_)
        self.imageWidth  = c_size_t(imageWidth)
        self.imageHeight = c_size_t(imageHeight)
        self.title       = c_char_p(title.encode("utf-8"))
        self.mode        = c_int(mode)
        self.offset      = c_size_t(offset)
        self.minimum     = c_double(minimum)
        if area is None:
            self.customArea = c_bool(False)
            self.area       = ImageArea()
        else:
            self.customArea = c_bool(True)
            self.area       = ImageArea()
            self.area.latT  = area["top"]
            self.area.latB  = area["bottom"]
            self.area.lonL  = area["left"]
            self.area.lonR  = area["right"]

        self.output = OutputImageAreas()


class Settings(Structure):
    _fields_ = [
        ("url", c_char_p),
        ("gzipped", c_bool),
        ("timeout", c_ulonglong),
        ("logName", c_char_p),
        ("verbose", c_bool),

        ("messageCount", c_size_t),
        ("messages", POINTER(MessageSettings)),
    ]

    def __init__(self, url, gzipped, verbose, logName, timeout, messages):
        Structure.__init__(self)

        self.messages_ = (MessageSettings * len(messages))()
        for i, message in enumerate(messages):
            self.messages_[i].set(**message)

        self.url          = c_char_p(url.encode("utf-8"))
        self.gzipped      = c_bool(gzipped)
        self.verbose      = c_bool(verbose)
        self.timeout      = c_ulonglong(timeout)
        self.logName      = c_char_p(logName.encode("utf-8"))
        self.messageCount = c_size_t(len(messages))
        self.messages     = cast(self.messages_, POINTER(MessageSettings))

class MRMSTypedReflSettings(Structure):
    _fields_ = [
        ("typeUrl", c_char_p),
        ("reflUrl", c_char_p),
        ("timeout", c_ulonglong),
        ("title", c_char_p),
        ("verbose", c_bool),
        ("gzipped", c_bool),

        ("tiled", c_bool),
        ("topLeftImageFile",     c_char_p),
        ("topRightImageFile",    c_char_p),
        ("bottomLeftImageFile",  c_char_p),
        ("bottomRightImageFile", c_char_p),

        ("rainPalette", POINTER(ColorTable)),
        ("snowPalette", POINTER(ColorTable)),
        ("hailPalette", POINTER(ColorTable)),
        ("minimum", c_double),
        ("imageWidth", c_size_t),
        ("imageHeight", c_size_t),
        ("mode", c_int),

        ("customArea", c_bool),
        ("area", ImageArea),
    ]

    def __init__(self,
                 typeUrl,
                 reflUrl,
                 timeout,
                 minimum,
                 title,
                 verbose,
                 gzipped,
                 imageFiles,
                 rainPalette,
                 snowPalette,
                 hailPalette,
                 imageWidth,
                 imageHeight,
                 mode,
                 area):
        Structure.__init__(self)

        if isinstance(imageFiles, str):
            self.tiled = c_bool(False)
            self.topLeftImageFile = c_char_p(imageFiles.encode("utf-8"))
        elif len(imageFiles) == 1:
            self.tiled = c_bool(False)
            self.topLeftImageFile = c_char_p(imageFiles[0].encode("utf-8"))
        elif len(imageFiles) == 4:
            self.tiled = c_bool(True)
            self.topLeftImageFile = c_char_p(imageFiles[0].encode("utf-8"))
            self.topRightImageFile = c_char_p(imageFiles[1].encode("utf-8"))
            self.bottomLeftImageFile = c_char_p(imageFiles[2].encode("utf-8"))
            self.bottomRightImageFile = c_char_p(imageFiles[3].encode("utf-8"))
        else:
            raise ValueError("imageFiles must be a string list with 1 item, or list with 4 items")

        if isinstance(mode, str):
            mode = RenderModes[mode]

        if isinstance(rainPalette, ColorTable):
            self.rainPalette_ = rainPalette
        else:
            self.rainPalette_ = ColorTable(rainPalette)

        if isinstance(snowPalette, ColorTable):
            self.snowPalette_ = snowPalette
        else:
            self.snowPalette_ = ColorTable(snowPalette)

        if isinstance(hailPalette, ColorTable):
            self.hailPalette_ = hailPalette
        else:
            self.hailPalette_ = ColorTable(hailPalette)

        self.typeUrl     = c_char_p(typeUrl.encode("utf-8"))
        self.reflUrl     = c_char_p(reflUrl.encode("utf-8"))
        self.timeout     = c_ulonglong(timeout)
        self.title       = c_char_p(title.encode("utf-8"))
        self.gzipped     = c_bool(gzipped)
        self.verbose     = c_bool(verbose)

        self.rainPalette = pointer(self.rainPalette_)
        self.snowPalette = pointer(self.snowPalette_)
        self.hailPalette = pointer(self.hailPalette_)
        self.minimum     = c_double(minimum)
        self.imageWidth  = c_size_t(imageWidth)
        self.imageHeight = c_size_t(imageHeight)
        self.mode        = c_int(mode)

        if area is None:
            self.customArea = c_bool(False)
            self.area       = ImageArea()
        else:
            self.customArea = c_bool(True)
            self.area       = ImageArea()
            self.area.latT  = area["top"]
            self.area.latB  = area["bottom"]
            self.area.lonL  = area["left"]
            self.area.lonR  = area["right"]

    def set_url(self, typeUrl, reflUrl):
        self.typeUrl = c_char_p(typeUrl.encode("utf-8"))
        self.reflUrl = c_char_p(reflUrl.encode("utf-8"))

class Grib2PfLib:
    PATHS_LINUX = [
        "{}/libgrib2pf.so",
        "{}/build/libgrib2pf.so",
        "libgrib2pf.so",
    ]
    PATHS_WIN = [
        "{}/grib2pf.dll",
        "{}/build/libgrib2pf.dll",
        "grib2pf",
    ]
    def __init__(self, path = None):
        location = os.path.split(__file__)[0]
        if path is None:
            if sys.platform.startswith('win'):
                paths = self.PATHS_WIN
            else:
                paths = self.PATHS_LINUX

            for p in paths:
                p = p.replace("{}", location)
                path = p
                if os.path.exists(path):
                    break

        self.lib = cdll.LoadLibrary(path)

    def generate_image(self, settings):
        if not isinstance(settings, Settings):
            raise TypeError("settings should be of type Settings")

        err = self.lib.generate_image(byref(settings))
        areas = []
        for i in range(settings.messageCount):
            areas.append({
                "topLeftArea": {
                    "lonL": round((settings.messages[i].output.topLeftArea.lonL - 180) % 360 - 180, 3),
                    "lonR": round((settings.messages[i].output.topLeftArea.lonR - 180) % 360 - 180, 3),
                    "latT": round(settings.messages[i].output.topLeftArea.latT, 3),
                    "latB": round(settings.messages[i].output.topLeftArea.latB, 3),
                },
                "topRightArea": {
                    "lonL": round((settings.messages[i].output.topRightArea.lonL - 180) % 360 - 180, 3),
                    "lonR": round((settings.messages[i].output.topRightArea.lonR - 180) % 360 - 180, 3),
                    "latT": round(settings.messages[i].output.topRightArea.latT, 3),
                    "latB": round(settings.messages[i].output.topRightArea.latB, 3),
                },
                "bottomLeftArea": {
                    "lonL": round((settings.messages[i].output.bottomLeftArea.lonL - 180) % 360 - 180, 3),
                    "lonR": round((settings.messages[i].output.bottomLeftArea.lonR - 180) % 360 - 180, 3),
                    "latT": round(settings.messages[i].output.bottomLeftArea.latT, 3),
                    "latB": round(settings.messages[i].output.bottomLeftArea.latB, 3),
                },
                "bottomRightArea": {
                    "lonL": round((settings.messages[i].output.bottomRightArea.lonL - 180) % 360 - 180, 3),
                    "lonR": round((settings.messages[i].output.bottomRightArea.lonR - 180) % 360 - 180, 3),
                    "latT": round(settings.messages[i].output.bottomRightArea.latT, 3),
                    "latB": round(settings.messages[i].output.bottomRightArea.latB, 3),
                },
            })

        return err, areas

    def generate_mrms_typed_refl(self, settings):
        if not isinstance(settings, MRMSTypedReflSettings):
            raise TypeError("settings should be of type MRMSTypedReflSettings")

        output = OutputImageAreas()

        err = self.lib.generate_mrms_typed_refl(byref(settings), byref(output))

        areas = {
            "topLeftArea": {
                "lonL": round((output.topLeftArea.lonL - 180) % 360 - 180, 3),
                "lonR": round((output.topLeftArea.lonR - 180) % 360 - 180, 3),
                "latT": round(output.topLeftArea.latT, 3),
                "latB": round(output.topLeftArea.latB, 3),
            },
            "topRightArea": {
                "lonL": round((output.topRightArea.lonL - 180) % 360 - 180, 3),
                "lonR": round((output.topRightArea.lonR - 180) % 360 - 180, 3),
                "latT": round(output.topRightArea.latT, 3),
                "latB": round(output.topRightArea.latB, 3),
            },
            "bottomLeftArea": {
                "lonL": round((output.bottomLeftArea.lonL - 180) % 360 - 180, 3),
                "lonR": round((output.bottomLeftArea.lonR - 180) % 360 - 180, 3),
                "latT": round(output.bottomLeftArea.latT, 3),
                "latB": round(output.bottomLeftArea.latB, 3),
            },
            "bottomRightArea": {
                "lonL": round((output.bottomRightArea.lonL - 180) % 360 - 180, 3),
                "lonR": round((output.bottomRightArea.lonR - 180) % 360 - 180, 3),
                "latT": round(output.bottomRightArea.latT, 3),
                "latB": round(output.bottomRightArea.latB, 3),
            },
        }

        return err, areas



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

