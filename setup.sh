#!/bin/sh
python3 -m pip install -r requirments.txt

echo '{
    "url": "https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz",
    "imageFile": "'$(pwd)'/baseReflectivity.png",
    "placeFile": "'$(pwd)'/baseReflectivity.txt",
    "verbose": true,
    "refresh": 15,
    "regenerateTime": 60
}' > settings.json
