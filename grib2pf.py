#!/usr/bin/env python3

import pygrib
import numpy as np
from PIL import Image
import requests
import gzip
import time
import re
import asyncio
import os

from aws import AWSHandler

TIME_FMT = "[%Y-%m-%d %H:%M:%S.{}]"

class Palette:
    COMBINE_SPACES_REGEX = re.compile(r"  +")
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
                            self.rf = self._parse_color(value, "rf", False)
                        elif name == "color":
                            self.values.append(self._parse_color(value, "color", True))
                        elif name == "color4":
                            self.values.append(self._parse_color(value, "color4", True))
                        elif name == "solidcolor":
                            color = self._parse_color(value, "color", False)
                            self.values.append(color + color[1:])
                        elif name == "solidcolor4":
                            color = self._parse_color(value, "color4", False)
                            self.values.append(color + color[1:])
                        else:
                            raise Exception(f"Unknown name {repr(name)}")
                    except Exception as e:
                        e.add_note(f"in color table {repr(filename)}, line {i + 1}\n{line}")
                        raise e
        self.values = sorted(self.values, key = lambda a: a[0])

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

    def get_at(self, v):
        # TODO RF?
        v = v * self.scale + self.offset
        if v < self.values[0][0]:
            return (0, 0, 0, 0)
        elif v >= self.values[-1][0]:
            value = self.values[-1]
            if len(value) == 5:
                return tuple(value[1:])
            elif len(value) == 9:
                return tuple(value[5:])
        for i, upper in enumerate(self.values[1:]):
            if upper[0] > v:
                lower = self.values[i]
                pos = (v - lower[0]) / (upper[0] - lower[0])

                lowerC = lower[1:5]

                if len(lower) == 8:
                    upperC = lower[5:]
                else:
                    upperC = upper[1:5]

                return tuple(int(pos * (upperC[j] - lowerC[j]) + lowerC[j]) for j in range(0, 4))
        raise Exception(f"Did not generate color from color table. This should be unreachable. value = {v} {self.values=}")

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
            verbose = False,
            timeout = 30):

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
        self.timeout = timeout

        self.grb = None
        self.latT = None
        self.latB = None
        self.lonL = None
        self.lonR = None

    def pull_data(self, url = None):
        if url is None:
            url = self.url
        try:
            self._log("Pulling data")
            res = requests.get(url, timeout = self.timeout)
            self.grb = pygrib.fromstring(gzip.decompress(res.content))
            self._log("Data pulled")
        except Exception as e:
            self._log(f"Failed to pull data with error '{e}'")


    def forget_data(self):
        self._log("Forgetting data")
        self.grb = None
        self.latT = None
        self.latB = None
        self.lonL = None
        self.lonR = None

    def _set_bounds(self, lats, lons):
        lons = lons[0]
        lats = lats.T[0]
        self.latT = round(lats.max(), 3)
        self.latB = round(lats.min(), 3)
        self.lonL = round(lons.min() - 360, 3)
        self.lonR = round(lons.max() - 360, 3)
        return lats, lons


    def generate_placefile(self):
        if self.grb is None:
            self._log("generate_placefile with no data")
            return

        self._log(f"Generating placefile {self.placeFile}")
        if self.latT is None:
            lats, lons = self.grb.latlons()
            self._set_bounds(lats, lons)

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
        if self.grb is None:
            self._log("generate_image with no data")
            return

        self._log("Preparing data")
        values, lats, lons = self.grb.data()

        lats, lons = self._set_bounds(lats, lons)

        xs = normalize(lons) * self.width
        ys = (1 - normalize(np.log(np.tan(np.pi / 4 + np.pi * lats / 360)))) * self.height

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
            t = time.strftime(TIME_FMT).format(format(round((time.time() % 1) * 1000), "0>3"))
            print(t, f"[{self.title}]", *args, **kwargs)

location = os.path.split(__file__)[0]

def replace_location(text):
    if isinstance(text, str):
        return text.replace("{_internal}", location)
    else:
        return text

async def run_setting(settings):
    placefile = GRIBPlacefile(
            settings.get("url", None),
            replace_location(settings.get("imageFile", None)),
            replace_location(settings.get("placeFile", None)),
            replace_location(settings.get("palette", None)),
            settings.get("title", "GRIB Placefile"),
            settings.get("refresh", 60),
            settings.get("imageURL", None),
            settings.get("imageWidth", 1920),
            settings.get("imageHeight", 1080),
            settings.get("verbose", False),
            settings.get("timeout", 30))

    if settings.get("aws", False):
        awsHandler = AWSHandler(settings["product"])

        while True:
            if awsHandler.update_key():
                placefile.pull_data(awsHandler.get_url())
                placefile.generate_image()
                placefile.generate_placefile()
                placefile.forget_data()
            await asyncio.sleep(settings.get("pullPeriod", 10))
        return



    last = time.time()
    placefile.pull_data()
    placefile.generate_image()
    placefile.generate_placefile()
    placefile.forget_data()

    if settings.get("regenerateTime", None) is not None:
        while True:
            now = time.time()
            dt = settings["regenerateTime"] - (now - last)
            if dt > 0:
                await asyncio.sleep(dt)

            last = time.time()
            placefile.pull_data()
            placefile.generate_image()
            placefile.generate_placefile()
            placefile.forget_data()

async def run_settings(settings):
    if isinstance(settings, dict):
        await run_setting(settings)
    elif isinstance(settings, list):
        async with asyncio.TaskGroup() as tg:
            for setting in settings:
                tg.create_task(run_setting(setting))

def main():
    import argparse
    import sys
    from jsonc_parser.parser import JsoncParser


    def choose_file():
        while True:
            print("Type the number of the file you want to select, and press enter")
            try:
                path = os.path.join(location, "presets")
                files = [file for file in os.listdir(path) if file.endswith(".jsonc")]
                for i, file in enumerate(files):
                    print(f"{i + 1}: {file}")
                index = int(input("number: ")) - 1
                return os.path.join(path, files[index])
            except KeyboardInterrupt:
                raise KeyboardInterrupt()
            except:
                print("invalid choice")



    def format_file(filename):
        return os.path.join(location, filename).replace("\\", "\\\\")

    defaultSettings = f"""
{{
    "url": "https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz",
    "imageFile": "{format_file('baseReflectivity.png')}",
    "placeFile": "{format_file('baseReflectivity.txt')}",
    "verbose": true,
    "refresh": 15,
    "regenerateTime": 60
}}
    """.strip()
    defaultSettingsPath  = os.path.join(location, "settings.jsonc")
    defaultSettingsPath2 = os.path.join(location, "settings.json")

    p = argparse.ArgumentParser(
            prog = "grib2pf",
            description = "Generate an GRIB placefile for use with Supercell-WX",
            fromfile_prefix_chars = "@")
    p.add_argument("--json", type = str,
                   help = """JSON representing your settings""")

    if len(sys.argv) == 1:
        if os.path.exists(defaultSettingsPath2):
            args = JsoncParser.parse_file(defaultSettingsPath2)
        elif os.path.exists(defaultSettingsPath):
            args = JsoncParser.parse_file(defaultSettingsPath)
        else:
            args = JsoncParser.parse_file(choose_file())
    elif len(sys.argv) == 3 and sys.argv[1] == "--json":
        args = JsoncParser.parse_str(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] not in ("-h", "--help"):
        args = JsoncParser.parse_file(sys.argv[1])
    else:
        raise Exception("Invalid Arguments")

    try:
        asyncio.run(run_settings(args))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
        if "exceptions" in dir(e):
            print(e.exceptions)
        input("Press enter to exit")
