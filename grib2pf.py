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

from aws import AWSHandler
from grib2pflib import Grib2PfLib, Settings, ColorTable, MRMSTypedReflSettings

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
            mode = "Nearest_Data",
            threshold = 0):

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
        self.mode = mode
        self.threshold = threshold

        self.proc = None

    def _generate(self):
        self._log(f"Generating image")
        settings = Settings(self.url,
                            self.gzipped,
                            self.verbose,
                            self.title,
                            self.timeout,
                            [{
                                "imageFile": self.imageFile,
                                "palette": self.palette,
                                "imageWidth": self.width,
                                "imageHeight": self.height,
                                "title": self.title,
                                "mode": self.mode,
                                "offset": 0,
                            }])
        lib = Grib2PfLib()
        err, lonL, lonR, latT, latB = lib.generate_image(settings)
        if err:
            sys.exit(err)

        latT = round(latT, 3)
        latB = round(latB, 3)
        lonL = round(lonL - 360, 3)
        lonR = round(lonR - 360, 3)

        self._log(f"Generating placefile {self.placeFile}")

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
        self.aws       = settings["aws"]
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

        self.settings = {
            "typeUrl":     settings.get("typeUrl", None),
            "reflUrl":     settings.get("reflUrl", None),
            "timeout":     settings.get("timeout", 30),
            "title":       settings.get("title", None),
            "verbose":     settings.get("verbose", False),
            "gzipped":     settings.get("gzipped", False),
            "imageFile":   replace_location(settings.get("imageFile", None)),
            "rainPalette": replace_location(settings.get("rainPalette", None)),
            "snowPalette": replace_location(settings.get("snowPalette", None)),
            "hailPalette": replace_location(settings.get("hailPalette", None)),
            "imageWidth":  settings.get("imageWidth", 1920),
            "imageHeight": settings.get("imageHeight", 1080),
            "mode":        settings.get("mode", "Average_Data"),
        }

    def _generate(self):
        self._log(f"Generating image")

        settings = MRMSTypedReflSettings(**self.settings)
        lib = Grib2PfLib()
        err, lonL, lonR, latT, latB = lib.generate_mrms_typed_refl(settings)
        if err:
            sys.exit(err)

        latT = round(latT, 3)
        latB = round(latB, 3)
        lonL = round(lonL - 360, 3)
        lonR = round(lonR - 360, 3)

        self._log(f"Generating placefile {self.placeFile}")

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
                settings.get("renderMode", "Average_Data"),
                settings.get("threshold", 0))

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

async def run_settings(settings):
    if isinstance(settings, dict):
        await run_setting(settings)
    elif isinstance(settings, list):
        async with asyncio.TaskGroup() as tg:
            for setting in settings:
                tg.create_task(run_setting(setting))

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
