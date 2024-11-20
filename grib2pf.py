#!/usr/bin/env python3

import pygrib
import numpy as np
from PIL import Image
import requests
import gzip

class Palette:
    def __init__(self, filename = None):
        self.scale  = 1
        self.offset = 0
        self.step   = None
        self.rf     = (0, 0, 0, 0)

        if filename is None:
            self.values = [
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
                self.values = []
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
                            try:
                                self.rf = self._parse_color(value, False, False)
                            except:
                                self.rf = self._parse_color(value, True, False)
                        elif name == "color":
                            self.values.append(self._parse_color(value, False, True))
                        elif name == "color4":
                            self.values.append(self._parse_color(value, True, True))
                        elif name == "solidcolor":
                            color = self._parse_color(value, False, False)
                            self.values.append(color, color[1:])
                        elif name == "solidcolor4":
                            color = self._parse_color(value, True, False)
                            self.values.append(color, color[1:])
                        else:
                            raise Exception(f"Unknown name {repr(name)}")
                    except Exception as e:
                        e.add_note(f"in color table {repr(filename)}, line {i + 1}\n{line}")
                        raise e
        self.values = sorted(self.values, key = lambda a: a[0])
        """
        self.values = [
            (10, 0, 22, 79, 200),
            (15, 0, 72, 114, 200),
            (20, 1, 131, 256, 200),
            (25, 2, 178, 189, 220),
            (30, 2, 233, 228, 220),
            (35, 225, 192, 0, 220),
            (40, 229, 135, 3, 220),
            (45, 240, 2, 7, 220),
            (50, 196, 0, 0, 220),
            (55, 158, 1, 3, 220),
            (60, 214, 50, 154, 220),
            (65, 162, 20, 145, 220),
            (80, 255, 255, 255, 220),
        ]
        """

    def _parse_color(self, text, alpha, optional):
        parts = text.split(" ")

        try:
            if alpha:
                if len(parts) == 5 or (optional and len(parts) == 8):
                    parts = [float(parts[0])] + [int(part) for part in parts[1:]]
                    return tuple(parts)
            else:
                if len(parts) == 4:
                    parts = [float(parts[0])] + [int(part) for part in parts[1:]] + [255]
                    return tuple(parts)
                elif optional and len(parts) == 7:
                    parts = [float(parts[0])] + \
                            [int(part) for part in parts[1:4]] + [255] + \
                            [int(part) for part in parts[4:7]] + [255]
        except:
            raise Exception(f"Could not parse color {repr(text)}")

        raise Exception(f"Could not parse color {repr(text)}")

    def get_at(self, v):
        # TODO idk if rf exists
        v = v * self.scale + self.offset
        if v < self.values[0][0]:
            return (0, 0, 0, 0)
        elif v >= self.values[-1][0]:
            value = self.values[-1]
            if len(value) == 4:
                return value[1:]
            else:
                return value[5:]
        for i, upper in enumerate(self.values[1:]):
            if upper[0] > v:
                lower = self.values[i - 1]
                pos = (v - lower[0]) / (upper[0] - lower[0])

                lowerC = lower[1:5]

                if len(lower) == 8:
                    upperC = lower[5:]
                else:
                    upperC = upper[1:5]

                return tuple(int(pos * (upperC[j] - lowerC[j]) + lowerC[j]) for j in range(0, 4))

def normalize(data):
    return (data  - data.min()) / (data.max() - data.min())

class GRIBPlacefile:
    PLACEFILE_TEMPLATE = """
Title: {title}
RefreshSeconds: {refresh}

Image: "{imageURL}"
    {latT}, {lonL}, 0, 0
    {latT}, {lonR}, 1, 0
    {latB}, {lonR}, 1, 1
    {latT}, {lonL}, 0, 0
    {latB}, {lonR}, 1, 1
    {latB}, {lonL}, 0, 1
End:
"""
    def __init__(
            self,
            url,
            imageFile,
            placeFile,
            palette = None,
            title = "GRIB Placefile",
            refresh = 60,
            imageURL = None,
            width = 1920,
            height = 1080,
            verbose = False):

        self.url = url
        self.imageFile = imageFile
        self.placeFile = placeFile
        if imageURL is None:
            imageURL = imageFile
        self.imageURL = imageURL
        if not isinstance(palette, Palette):
            palette = Palette(palette)
        self.palette = palette
        self.title = title
        self.refresh = refresh
        self.width = width
        self.height = height
        self.verbose = verbose

        self.grb = None
        self.latT = None
        self.latB = None
        self.lonL = None
        self.lonR = None

    def pull_data(self):
        self._log("Pulling data")
        res = requests.get(self.url)
        self.grb = pygrib.fromstring(gzip.decompress(res.content))
        self._log("Data pulled")

    def forget_data(self):
        self._log("Forgetting data")
        self.grb = None
        self.latT = None
        self.latB = None
        self.lonL = None
        self.lonR = None

    def generate_placefile(self):
        self._log("Generating placefile")
        if self.latT is None:
            lats, lons = self.grb.latlons()
            self.latT = round(lats.max(), 3)
            self.latB = round(lats.min(), 3)
            self.lonL = round(lons.min() - 360, 3)
            self.lonR = round(lons.max() - 360, 3)

        with open(self.placeFile, "w") as file:
            file.write(self.PLACEFILE_TEMPLATE.format(
                    title = self.title,
                    refresh = self.refresh,
                    imageURL = self.imageURL,
                    latT = self.latT,
                    latB = self.latB,
                    lonL = self.lonL,
                    lonR = self.lonR
                ))

    def generate_image(self):
        self._log("Preparing data")
        values, lats, lons = self.grb.data()

        self.latT = round(lats.max(), 3)
        self.latB = round(lats.min(), 3)
        self.lonL = round(lons.min() - 360, 3)
        self.lonR = round(lons.max() - 360, 3)


        xs = normalize(lons[0]) * self.width
        ys = (1 - normalize(np.log(np.tan(np.pi / 4 + np.pi * lats.T[0] / 360)))) * self.height 

        self._log("Rendering image")
        imageToDataX = np.zeros(self.width, dtype = np.int64)
        current = 0
        for i in range(self.width):
            while current + 1 < len(xs) and abs(xs[current] - i - .5) > abs(xs[current + 1] - i - .5):
                current += 1
            imageToDataX[i] = current

        imageToDataY = np.zeros(self.height, dtype = np.int64)
        current = 0
        for i in range(self.height):
            while current + 1 < len(ys) and abs(ys[current] - i - .5) > abs(ys[current + 1] - i - .5):
                current += 1
            imageToDataY[i] = current

        image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        px = image.load()
        palette = self.palette # this removes a dictionary access for every pixel
        for y in range(self.height):
            dataRow = values[imageToDataY[y]]
            for x in range(self.width):
                px[x, y] = palette.get_at(dataRow[imageToDataX[x]])

        self._log("Saving image")
        image.save(self.imageFile)

    def _log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

if __name__ == "__main__":
    import argparse
    import time
    import sys
    import json

    """
    url,
    imageFile,
    placeFile,
    palette = None,
    title = "GRIB Placefile",
    refresh = 1,
    imageURL = None,
    width = 1920,
    height = 1080):
    """
    p = argparse.ArgumentParser(
            prog = "grib2pf",
            description = "Generate an GRIB placefile for use with Supercell-WX",
            fromfile_prefix_chars = "@")
    p.add_argument("url", type = str,
                   help = """The URL to pull from. Should probably come from "https://mrms.ncep.noaa.gov/data"
                   "https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz" is a useful reflectivity plot""")
    p.add_argument("imageFile", type = str,
                   help = "The file name were the image should be written. Should be an absolute path to a png.")
    p.add_argument("placeFile", type = str,
                   help = "The file name were the placefile should be written")
    p.add_argument("--palette", "-p", type = str, default = None,
                   help = "The path to a GRS color table to use for this plot")
    p.add_argument("--title", "-t", type = str, default = "GRIB Placefile",
                   help = "The title to display in Supercell-WX")
    p.add_argument("--refresh", "-r", type = int, default = 60,
                   help = "How often Supercell-WX should refresh the placefile, in seconds")
    p.add_argument("--imageURL", "-i", type = str, default = None,
                   help = "The URL at which the image will be hosted, Unnecessary for local usage only")
    p.add_argument("--imageWidth", "-W", type = int, default = 1920,
                   help = "The width of the image to be generated. Only effects the resolution on the plot")
    p.add_argument("--imageHeight", "-H", type = int, default = 1080,
                   help = "The height of the image to be generated. Only effects the resolution on the plot")
    p.add_argument("--regenerateTime", "-T", type = int, default = None,
                   help = "How often to regenerate the image and placefile in seconds. Defaults to not regenerating")
    p.add_argument("--verbose", "-v", action = "store_true", default = False,
                   help = "Print status messages")

    if len(sys.argv) == 2 and sys.argv[1] not in ("-h", "--help"):
        with open(sys.argv[1]) as file:
            args = json.load(file)
    else:
        args = vars(p.parse_args())

    placefile = GRIBPlacefile(
            args.get("url", None),
            args.get("imageFile", None),
            args.get("placeFile", None),
            args.get("palette", None),
            args.get("title", "GRIB Placefile"),
            args.get("refresh", 60),
            args.get("imageURL", None),
            args.get("imageWidth", 1920),
            args.get("imageHeight", 1080),
            args.get("verbose", False))

    last = time.time()
    placefile.pull_data()
    placefile.generate_image()
    placefile.generate_placefile()
    placefile.forget_data()

    if args.get("regenerateTime", None) is not None:
        try:
            while True:
                now = time.time()
                dt = args["regenerateTime"] - (now - last)
                if dt > 0:
                    time.sleep(dt)

                last = time.time()
                placefile.pull_data()
                placefile.generate_image()
                placefile.generate_placefile()
                placefile.forget_data()
        except KeyboardInterrupt:
            exit()
