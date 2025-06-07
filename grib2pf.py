#!/usr/bin/env python3

import requests
import gzip
import time
import re
import asyncio
import os
import multiprocessing
from multiprocessing import Process
import sys

from aws import AWSHandler, AWSHRRRHandler
from grib2pflib import Grib2PfLib, Settings, ColorTable, MRMSTypedReflSettings
from nomads import rtma2p5_ru_get_url

location = os.path.split(__file__)[0]

def replace_location(text):
    if isinstance(text, str):
        return text.replace("{_internal}", location)
    else:
        return text

TIME_FMT = "[%Y-%m-%d %H:%M:%S.{}]"

def normalize(data):
    return (data  - data.min()) / (data.max() - data.min())

PLACEFILE_TEMPLATE = """
Title: {title}
RefreshSeconds: {refresh}
Threshold: {threshold}

Image: "{imageURL}"
    {latT}, {lonL}, 0, 0
    {latT}, {lonR}, 1, 0
    {latB}, {lonR}, 1, 1
    {latT}, {lonL}, 0, 0
    {latB}, {lonR}, 1, 1
    {latB}, {lonL}, 0, 1
End:
"""
TILED_PLACEFILE_TEMPLATE = """
Title: {title}
RefreshSeconds: {refresh}
Threshold: {threshold}

Image: "{imageURLs[0]}"
    {areas[topLeftArea][latT]}, {areas[topLeftArea][lonL]}, 0, 0
    {areas[topLeftArea][latT]}, {areas[topLeftArea][lonR]}, 1, 0
    {areas[topLeftArea][latB]}, {areas[topLeftArea][lonR]}, 1, 1
    {areas[topLeftArea][latT]}, {areas[topLeftArea][lonL]}, 0, 0
    {areas[topLeftArea][latB]}, {areas[topLeftArea][lonR]}, 1, 1
    {areas[topLeftArea][latB]}, {areas[topLeftArea][lonL]}, 0, 1
End:
Image: "{imageURLs[1]}"
    {areas[topRightArea][latT]}, {areas[topRightArea][lonL]}, 0, 0
    {areas[topRightArea][latT]}, {areas[topRightArea][lonR]}, 1, 0
    {areas[topRightArea][latB]}, {areas[topRightArea][lonR]}, 1, 1
    {areas[topRightArea][latT]}, {areas[topRightArea][lonL]}, 0, 0
    {areas[topRightArea][latB]}, {areas[topRightArea][lonR]}, 1, 1
    {areas[topRightArea][latB]}, {areas[topRightArea][lonL]}, 0, 1
End:
Image: "{imageURLs[2]}"
    {areas[bottomLeftArea][latT]}, {areas[bottomLeftArea][lonL]}, 0, 0
    {areas[bottomLeftArea][latT]}, {areas[bottomLeftArea][lonR]}, 1, 0
    {areas[bottomLeftArea][latB]}, {areas[bottomLeftArea][lonR]}, 1, 1
    {areas[bottomLeftArea][latT]}, {areas[bottomLeftArea][lonL]}, 0, 0
    {areas[bottomLeftArea][latB]}, {areas[bottomLeftArea][lonR]}, 1, 1
    {areas[bottomLeftArea][latB]}, {areas[bottomLeftArea][lonL]}, 0, 1
End:
Image: "{imageURLs[3]}"
    {areas[bottomRightArea][latT]}, {areas[bottomRightArea][lonL]}, 0, 0
    {areas[bottomRightArea][latT]}, {areas[bottomRightArea][lonR]}, 1, 0
    {areas[bottomRightArea][latB]}, {areas[bottomRightArea][lonR]}, 1, 1
    {areas[bottomRightArea][latT]}, {areas[bottomRightArea][lonL]}, 0, 0
    {areas[bottomRightArea][latB]}, {areas[bottomRightArea][lonR]}, 1, 1
    {areas[bottomRightArea][latB]}, {areas[bottomRightArea][lonL]}, 0, 1
End:
"""

class GRIBPlacefile:
    def __init__(
            self,
            url,
            imageFile,
            placeFile,
            gzipped = True,
            palette = None,
            title = "GRIB Placefile",
            refresh = 60,
            imageURL = None,
            width = 1920,
            height = 1080,
            verbose = False,
            timeout = 30,
            minimum = -998,
            contour = False,
            mode = "Nearest_Data",
            threshold = 0,
            area = None):

        self.url = url
        self.imageFile = imageFile
        self.placeFile = placeFile
        self.gzipped = gzipped
        if imageURL is None:
            imageURL = imageFile
        self.imageURL = imageURL
        self.palette = palette
        self.title = title
        self.refresh = refresh
        self.width = width
        self.height = height
        self.verbose = verbose
        self.timeout = timeout
        self.minimum = minimum
        self.contour = contour
        self.mode = mode
        self.threshold = threshold
        self.area = area

        self.proc = None

    def _generate(self):
        self._log(f"Generating image")
        tiled = self.width > 2048 or self.height > 2048

        if tiled:
            imageFiles = [
                self.imageFile.replace("{}", "TopLeft"),
                self.imageFile.replace("{}", "TopRight"),
                self.imageFile.replace("{}", "BottomLeft"),
                self.imageFile.replace("{}", "BottomRight"),
            ]
        else:
            imageFiles = [self.imageFile]

        settings = Settings(self.url,
                            self.gzipped,
                            self.verbose,
                            self.title,
                            self.timeout,
                            [{
                                "imageFiles": imageFiles,
                                "palette": self.palette,
                                "imageWidth": self.width,
                                "imageHeight": self.height,
                                "title": self.title,
                                "mode": self.mode,
                                "offset": 0,
                                "minimum": self.minimum,
                                "contour": self.contour,
                                "area": self.area
                            }])
        lib = Grib2PfLib()
        err, areas = lib.generate_image(settings)
        if err:
            sys.exit(err)


        self._log(f"Generating placefile {self.placeFile}")
        if tiled:
            imageURLs = [
                self.imageURL.replace("{}", "TopLeft"),
                self.imageURL.replace("{}", "TopRight"),
                self.imageURL.replace("{}", "BottomLeft"),
                self.imageURL.replace("{}", "BottomRight"),
            ]
            with open(self.placeFile, "w") as file:
                file.write(TILED_PLACEFILE_TEMPLATE.format(
                        title = self.title,
                        refresh = self.refresh,
                        imageURLs = imageURLs,
                        areas = areas[0],
                        threshold = self.threshold,
                    ))
        else:
            area = areas[0]
            latT = area["topLeftArea"]["latT"]
            latB = area["topLeftArea"]["latB"]
            lonL = area["topLeftArea"]["lonL"]
            lonR = area["topLeftArea"]["lonR"]


            with open(self.placeFile, "w") as file:
                file.write(PLACEFILE_TEMPLATE.format(
                        title = self.title,
                        refresh = self.refresh,
                        imageURL = self.imageURL,
                        latT = latT,
                        latB = latB,
                        lonL = lonL,
                        lonR = lonR,
                        threshold = self.threshold,
                    ))
        self._log("Finished generating")
        sys.exit(0)

    def generate(self, url = None):
        if url is not None:
            self.url = url

        if self.proc is not None and self.proc.is_alive():
            self._log("Killing old process. Likely failed to update.")
            self.proc.kill()
            self.proc.join()
            self.proc.close()
        if self.proc is not None:
            self.proc.close()

        self.proc = Process(target = self._generate, daemon = True)
        self.proc.start()

    def _log(self, *args, **kwargs):
        if self.verbose:
            t = time.strftime(TIME_FMT).format(format(round((time.time() % 1) * 1000), "0>3"))
            print(t, f"[{self.title}]", *args, **kwargs)

class MRMSTypedReflectivityPlacefile:
    def __init__(self, settings):
        self.proc = None
        self.aws = settings["aws"]
        if self.aws:
            self.typeAWS = AWSHandler(settings["typeProduct"])
            self.reflAWS = AWSHandler(settings["reflProduct"])
            self.typeRefreshNeeded = False
            self.reflRefreshNeeded = False

        self.title     = settings.get("title", None)
        self.verbose   = settings.get("verbose", False)
        self.refresh   = settings.get("refresh", 15)
        self.imageURL  = settings.get("imageURL", replace_location(settings["imageFile"]))
        self.placeFile = replace_location(settings.get("placeFile", ""))
        self.threshold = settings.get("threshold", 0)

        imageFile = replace_location(settings.get("imageFile", None))
        self.tiled = ("imageWidth" in settings and settings["imageWidth"] > 2048) or \
                     ("imageHeight" in settings and settings["imageHeight"] > 2048)
        if self.tiled:
            imageFiles = [
                imageFile.replace("{}", "TopLeft"),
                imageFile.replace("{}", "TopRight"),
                imageFile.replace("{}", "BottomLeft"),
                imageFile.replace("{}", "BottomRight"),
            ]
        else:
            imageFiles = [imageFile]

        self.settings = {
            "typeUrl":     settings.get("typeUrl", None),
            "reflUrl":     settings.get("reflUrl", None),
            "timeout":     settings.get("timeout", 30),
            "minimum":     settings.get("minimum", -998),
            "title":       settings.get("title", None),
            "verbose":     settings.get("verbose", False),
            "gzipped":     settings.get("gzipped", False),
            "imageFiles":  imageFiles,
            "rainPalette": replace_location(settings.get("rainPalette", None)),
            "snowPalette": replace_location(settings.get("snowPalette", None)),
            "hailPalette": replace_location(settings.get("hailPalette", None)),
            "imageWidth":  settings.get("imageWidth", 1920),
            "imageHeight": settings.get("imageHeight", 1080),
            "mode":        settings.get("renderMode", "Average_Data"),
            "area":        settings.get("area", None),
        }

    def _generate(self):
        self._log(f"Generating image")

        settings = MRMSTypedReflSettings(**self.settings)
        lib = Grib2PfLib()
        err, areas = lib.generate_mrms_typed_refl(settings)
        if err:
            self._log(f"Error generating image, {err}")
            sys.exit(err)

        self._log(f"Generating placefile {self.placeFile}")

        if self.tiled:
            imageURLs = [
                self.imageURL.replace("{}", "TopLeft"),
                self.imageURL.replace("{}", "TopRight"),
                self.imageURL.replace("{}", "BottomLeft"),
                self.imageURL.replace("{}", "BottomRight"),
            ]
            with open(self.placeFile, "w") as file:
                file.write(TILED_PLACEFILE_TEMPLATE.format(
                        title = self.title,
                        refresh = self.refresh,
                        imageURLs = imageURLs,
                        areas = areas,
                        threshold = self.threshold,
                    ))
        else:
            latT = areas["topLeftArea"]["latT"]
            latB = areas["topLeftArea"]["latB"]
            lonL = areas["topLeftArea"]["lonL"]
            lonR = areas["topLeftArea"]["lonR"]

            with open(self.placeFile, "w") as file:
                file.write(PLACEFILE_TEMPLATE.format(
                        title = self.title,
                        refresh = self.refresh,
                        imageURL = self.imageURL,
                        latT = latT,
                        latB = latB,
                        lonL = lonL,
                        lonR = lonR,
                        threshold = self.threshold,
                    ))

        self._log("Finished generating")
        sys.exit(0)

    def generate(self):
        if self.aws:
            self.typeRefreshNeeded = self.typeAWS.update_key() or self.typeRefreshNeeded
            self.reflRefreshNeeded = self.reflAWS.update_key() or self.reflRefreshNeeded

            if not (self.typeRefreshNeeded and self.reflRefreshNeeded):
                return
            self.settings["typeUrl"] = self.typeAWS.get_url()
            self.settings["reflUrl"] = self.reflAWS.get_url()
            self.typeRefreshNeeded = False
            self.reflRefreshNeeded = False

            typeAWS = self.typeAWS
            reflAWS = self.reflAWS
            self.typeAWS = None
            self.reflAWS = None

        if self.proc is not None and self.proc.is_alive():
            self._log("Killing old process. Likely failed to update.")
            self.proc.kill()
            self.proc.join()
            self.proc.close()
        if self.proc is not None:
            self.proc.close()

        self.proc = Process(target = self._generate, daemon = True)
        self.proc.start()

        if self.aws:
            self.typeAWS = typeAWS
            self.reflAWS = reflAWS

    def _log(self, *args, **kwargs):
        if self.verbose:
            t = time.strftime(TIME_FMT).format(format(round((time.time() % 1) * 1000), "0>3"))
            print(t, f"[{self.title}]", *args, **kwargs)

class HRRRPlaceFiles:
    def __init__(self, hrrrs):
        self.hrrrs = hrrrs
        self.proc  = None

        self.timeout = 3600
        self.logName = "HRRR " + hrrrs[0]["product"]["fileType"]
        self.products = {}

        for i, hrrr in enumerate(hrrrs):
            self.timeout = min(hrrr.get("timeout", 30), self.timeout)
            self.products[hrrr["product"]["productId"]] = i

        self.aws = AWSHRRRHandler(self.hrrrs[0]["product"])
        self.verbose = True

    def _get_offsets(self, indexURL):
        offsets = [-1] * len(self.hrrrs)
        res = requests.get(indexURL, timeout = self.timeout)
        for line in res.text.splitlines():
            _, offset, date, ID = line.split(":", 3)
            if ID in self.products:
                offsets[self.products[ID]] = int(offset)

        for i in range(len(offsets)):
            if offsets[i] == -1:
                self._log("Could not find a product")
                offsets[i] = 0

        return offsets

    def _generate(self, url, indexURL):
        self._log(f"Generating images")

        offsets = self._get_offsets(indexURL)
        messages = []
        for hrrr, offset in zip(self.hrrrs, offsets):
            messages.append({
                "imageFiles":  hrrr["imageFile"],
                "palette":     hrrr.get("palette", None),
                "imageWidth":  hrrr.get("imageWidth", 1920),
                "imageHeight": hrrr.get("imageHeight", 1080),
                "title":       hrrr.get("title", "HRRR Data"),
                "mode":        hrrr.get("mode", "Nearest_Data"),
                "minimum":     hrrr.get("minimum", -998),
                "contour":     hrrr.get("contour", False),
                "area":        hrrr.get("area", None),
                "offset":      offset,
                })

        settings = Settings(
                url = url,
                gzipped = False,
                timeout = self.timeout,
                logName = self.logName,
                verbose = True,
                messages = messages
            )

        lib = Grib2PfLib()
        err, areas = lib.generate_image(settings)
        if err:
            self._log(f"Error generating image, {err}")
            sys.exit(err)


        for hrrr, area in zip(self.hrrrs, areas):
            self._log(f"Generating placefile {hrrr['placeFile']}", title =
                      hrrr.get("title", "HRRR Data"))

            latT = area["topLeftArea"]["latT"]
            latB = area["topLeftArea"]["latB"]
            lonL = area["topLeftArea"]["lonL"]
            lonR = area["topLeftArea"]["lonR"]

            with open(hrrr["placeFile"], "w") as file:
                file.write(PLACEFILE_TEMPLATE.format(
                        title = hrrr.get("title", "HRRR Data"),
                        refresh = hrrr.get("refresh", 15),
                        imageURL = hrrr.get("imageURL", hrrr["imageFile"]),
                        latT = latT,
                        latB = latB,
                        lonL = lonL,
                        lonR = lonR,
                        threshold = hrrr.get("threshold", 0),
                    ))
        self._log("Finished generating")
        sys.exit(0)

    def generate(self):
        if not self.aws.update_key():
            return

        if self.proc is not None and self.proc.is_alive():
            self._log("Killing old process. Likely failed to update.")
            self.proc.kill()
            self.proc.join()
            self.proc.close()
            self.proc = None
        elif self.proc is not None:
            print("clossing process")
            self.proc.close()
            self.proc = None

        url      = self.aws.get_url(False)
        indexURL = self.aws.get_url(True)

        aws = self.aws
        self.aws = None

        self.proc = Process(target = self._generate, args = (url, indexURL),
                            daemon = True)
        self.proc.start()

        self.aws = aws

    def _log(self, *args, **kwargs):
        if "title" in kwargs:
            logName = kwargs.pop("title")
        else:
            logName = self.logName

        if self.verbose:
            t = time.strftime(TIME_FMT).format(format(round((time.time() % 1) * 1000), "0>3"))
            print(t, f"[{logName}]", *args, **kwargs)

class NomadsIndexedPlaceFiles:
    def __init__(self, settings, getUrl, name):
        self.settings = settings
        self.getUrl   = getUrl
        self.proc     = None
        self.lastUrl  = None

        self.timeout = 3600
        self.logName = "NOMADS indexed " + name
        self.products = {}
        self.verbose = True

        for i, setting in enumerate(settings):
            self.timeout = min(setting.get("timeout", 30), self.timeout)
            self.products[setting["product"]] = i


    def _get_offsets(self, indexURL):
        offsets = [-1] * len(self.settings)
        res = requests.get(indexURL, timeout = self.timeout)
        for line in res.text.splitlines():
            _, offset, date, ID = line.split(":", 3)
            if ID in self.products:
                offsets[self.products[ID]] = int(offset)

        for i in range(len(offsets)):
            if offsets[i] == -1:
                self._log("Could not find a product")
                offsets[i] = 0

        return offsets

    def _generate(self, url, indexURL):
        self._log(f"Generating images")

        offsets = self._get_offsets(indexURL)
        messages = []
        for setting, offset in zip(self.settings, offsets):
            messages.append({
                "imageFiles":  setting["imageFile"],
                "palette":     setting.get("palette", None),
                "imageWidth":  setting.get("imageWidth", 1920),
                "imageHeight": setting.get("imageHeight", 1080),
                "title":       setting.get("title", "HRRR Data"),
                "mode":        setting.get("mode", "Nearest_Data"),
                "minimum":     setting.get("minimum", -998),
                "contour":     setting.get("contour", False),
                "area":        setting.get("area", None),
                "offset":      offset,
                })

        settings = Settings(
                url = url,
                gzipped = False,
                timeout = self.timeout,
                logName = self.logName,
                verbose = True,
                messages = messages
            )

        lib = Grib2PfLib()
        err, areas = lib.generate_image(settings)
        if err:
            self._log(f"Error generating image, {err}")
            sys.exit(err)


        for setting, area in zip(self.settings, areas):
            self._log(f"Generating placefile {setting['placeFile']}", title =
                      setting.get("title", "HRRR Data"))

            latT = area["topLeftArea"]["latT"]
            latB = area["topLeftArea"]["latB"]
            lonL = area["topLeftArea"]["lonL"]
            lonR = area["topLeftArea"]["lonR"]

            with open(setting["placeFile"], "w") as file:
                file.write(PLACEFILE_TEMPLATE.format(
                        title = setting.get("title", "HRRR Data"),
                        refresh = setting.get("refresh", 15),
                        imageURL = setting.get("imageURL", setting["imageFile"]),
                        latT = latT,
                        latB = latB,
                        lonL = lonL,
                        lonR = lonR,
                        threshold = setting.get("threshold", 0),
                    ))
        self._log("Finished generating")
        sys.exit(0)

    def generate(self):
        if self.proc is not None and self.proc.is_alive():
            self._log("Killing old process. Likely failed to update.")
            self.proc.kill()
            self.proc.join()
            self.proc.close()
            self.proc = None
        elif self.proc is not None:
            self.proc.close()
            self.proc = None

        url = self.getUrl()
        if url is None or self.lastUrl == url:
            return
        self.lastUrl = url
        indexURL = url + ".idx"

        self.proc = Process(target = self._generate, args = (url, indexURL),
                            daemon = True)
        self.proc.start()

    def _log(self, *args, **kwargs):
        if "title" in kwargs:
            logName = kwargs.pop("title")
        else:
            logName = self.logName

        if self.verbose:
            t = time.strftime(TIME_FMT).format(format(round((time.time() % 1) * 1000), "0>3"))
            print(t, f"[{logName}]", *args, **kwargs)


async def run_setting(settings):
    mainType = settings.get("mainType", "basic")
    if mainType == "basic":
        palette = replace_location(settings.get("palette"))
        if not sys.platform.startswith('win'): # Windows...cant...fork?
            palette = ColorTable(palette)
        placefile = GRIBPlacefile(
                settings.get("url", None),
                replace_location(settings.get("imageFile", None)),
                replace_location(settings.get("placeFile", None)),
                replace_location(settings.get("gzipped", True)),
                palette,
                settings.get("title", "GRIB Placefile"),
                settings.get("refresh", 60),
                settings.get("imageURL", None),
                settings.get("imageWidth", 1920),
                settings.get("imageHeight", 1080),
                settings.get("verbose", False),
                settings.get("timeout", 30),
                settings.get("minimum", -998),
                settings.get("contour", False),
                settings.get("renderMode", "Average_Data"),
                settings.get("threshold", 0),
                settings.get("area", None))

        if settings.get("aws", False):
            awsHandler = AWSHandler(settings["product"])

            while True:
                if awsHandler.update_key():
                    placefile.generate(awsHandler.get_url())
                await asyncio.sleep(settings.get("pullPeriod", 10))
            return

        last = time.time()
        placefile.generate()

        if settings.get("regenerateTime", None) is not None:
            while True:
                now = time.time()
                dt = settings["regenerateTime"] - (now - last)
                if dt > 0:
                    await asyncio.sleep(dt)

                last = time.time()
                placefile.generate()
    elif mainType == "MRMSTypedReflectivity":
        placefile = MRMSTypedReflectivityPlacefile(settings)

        if settings.get("aws", False):
            while True:
                placefile.generate()
                await asyncio.sleep(settings.get("pullPeriod", 10))
            return

        last = time.time()
        placefile.generate()

        if settings.get("regenerateTime", None) is not None:
            while True:
                now = time.time()
                dt = settings["regenerateTime"] - (now - last)
                if dt > 0:
                    await asyncio.sleep(dt)

                last = time.time()
                placefile.generate()

async def run_hrrrs(hrrrs):
    placefile = HRRRPlaceFiles(hrrrs)
    while True:
        placefile.generate()
        await asyncio.sleep(hrrrs[0].get("pullPeriod", 10))

async def run_rtma2p5_rus(settings):
    placefile = NomadsIndexedPlaceFiles(settings, rtma2p5_ru_get_url, "RTMA2p5 RU")
    while True:
        placefile.generate()
        await asyncio.sleep(settings[0].get("pullPeriod", 10))

async def run_settings(settings):
    if isinstance(settings, dict):
        # TODO color
        print("WARNING: The settings format you are using is depricated. Recommend switching to using a list of objects.")
        await run_setting(settings)
    elif isinstance(settings, list):
        async with asyncio.TaskGroup() as tg:
            hrrrs = {}
            rtma2p5_rus = []
            for setting in settings:
                match setting.get("mainType", ""):
                    case "HRRR":
                        location = setting["product"]["location"]
                        fileType = setting["product"]["fileType"]

                        hrrrs.setdefault(location, {})
                        hrrrs[location].setdefault(fileType, [])

                        hrrrs[location][fileType].append(setting)
                    case "RTMA2P5_RU":
                        rtma2p5_rus.append(setting)
                    case _:
                        tg.create_task(run_setting(setting))
            if len(hrrrs) > 0:
                for location in hrrrs.values():
                    for fileType in location.values():
                        tg.create_task(run_hrrrs(fileType))
            if len(rtma2p5_rus) > 0:
                tg.create_task(run_rtma2p5_rus(rtma2p5_rus))


def main():
    import argparse
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
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    import traceback
    try:
        main()
    except Exception as e:
        traceback.print_exception(e)
        input("Press enter to exit")
