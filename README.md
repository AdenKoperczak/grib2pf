# grib2pf
This is a python script which takes GRIB data (mainly MRMS) and outputs it to a
placefile for usage with Supercell-Wx. This adds the ability for nation wide
weather radar in Supercell-Wx.

## Setup Guide Windows
There are 2 main ways to run this in Windows: WSL or via an executable. For
WSL follow the Linux instructions. These instructions are for the executable.

### Windows Dependencies
You will need the latest Microsoft Visual C++ Runtime to run this program. If
you have Supercell-Wx v4.5.0 running on your system, then you should already
have them. Otherwise download them from
https://aka.ms/vs/17/release/vc\_redist.x64.exe .

### Download The Executable
Download the executable and extract it. You will want to extract it to a
permanent location. This program does not install itself, so where you place it
is where it will be installed.

### Run It
For a basic run, you can simply double click on `grib2pf.exe` or `grib2pf`.
This will put a basic settings file (`settings.json`) in the `_internal` folder.
It should look like bellow, where `{_internal folder}` is replaced by the path
to the `_internal` folder.
```
{
    "url": "https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz",
    "imageFile": "{_internal folder}\\baseReflectivity.png",
    "placeFile": "{_internal folder}\\baseReflectivity.txt",
    "verbose": true,
    "refresh": 15,
    "regenerateTime": 60
}
```
This will generate a base reflectivity placefile. The "URL" for this placefile
with simple be the path following `placeFile` (You may need to change `\\` to
`\`). This setup will update the placefile every minute. Updating the placefile
is somewhat slow, and the MRMS data is only updated every two minutes, so this
should be enough. In order to stop it use press CTRL-C in the window it
launches.

### Using Multiple Placefiles
One way to have multiple placefiles is to simply copy the `grib2pf` folder.
Each folder will have its own settings files. Just make sure that the paths
in `settings.json` do not overlap.

Another way to generate multiple placefiles by having multiple settings files.
By default, `grib2pf` only uses the `_internal/settings.json` file, but this
can be changed. Probably the easiest way is to create a shortcut to launch
grib2pf with an argument. In the `Create Shortcut` dialog, simply enter the
path to `grib2pf.exe` followed by a space, and then the path to your settings
file. You may want to use quotes around the paths. Below is an example.
```
"C:\Users\user\Documents\grib2pf\grib2pf.exe" "C:\Users\user\Documents\grib2pf\settings2.json"
```
Double clicking on this shortcut will launch `grib2pf` using the given settings
file.

## Installing on Linux
To install on Linux you can simply download or clone the repository, then run
the following command to install all dependencies.
```
pip install -r requirements.txt
```
You can then run `grib2pf.py` as a normal script.

This will only work if your distro does not manage your Python packages.
Otherwise, you can use a Python virtual environment. To do so, do the
following.
```
python3 -m venv venv
./venv/bin/pip -r requirements.txt
```
In order to run `grib2pf.py`, use
```
./venv/bin/python grib2pf.py
```

If you are using WSL, you will want to modify the path to output the placefile
and image in `settings.json` to a folder accessible by Windows.

## Adding To Supercell-Wx
Copy the path to the placefile, and use it as the URL for a placefile in
Supercell-Wx. It is recommended to place your grib placefile layer(s) below the
radar layer. The local radar will have a higher resolution, and have more
plots. You could also only enable the grib placefile layer(s) on specific
panes.

## Arguments
When run without an argument, `grib2pf` will run using the settings file in the
install directory (`grib2pf` on Linux, and `grib2pf\_internal` on Windows).
When run with one argument, `grib2pf` will use that argument as the path to a
settings file. Otherwise, `grib2pf` can be run without a settings file, using
arguments instead. The arguments documentation can be seen by running `grib2pf`
with `--help`. The arguments align with the settings described below.

## Settings
Below are all the settings supported by this program.

`url`: The URL to pull from. Should probably come from
"https://mrms.ncep.noaa.gov/data"
"https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS\_MergedBaseReflectivity.latest.grib2.gz"
is a useful reflectivity plot. Descriptions of the plots can be found at
(https://www.nssl.noaa.gov/projects/mrms/operational/tables.php)

`imageFile`: The file name were the image should be written. Should be an
absolute path to a png

`placeFile`: The file name were the placefile should be written

`palette`: The path to a GRS color table to use for this plot. Useful for non
reflectivity plots. Defaults to [NOAA's Weather and Climate
Toolkit](https://www.ncdc.noaa.gov/wct/) reflectivity palette.

`title`: The title to display in Supercell-Wx

`refresh`: How often Supercell-Wx should refresh the placefile, in seconds

`imageURL`: The URL at which the image will be hosted. Unnecessary for local
usage, but useful for web hosting

`imageWidth`: The width of the image to be generated. Only effects the resolution
off the plot

`imageHeight`: The height of the image to be generated. Only effects the
resolution off the plot

`regenerateTime`: How often to regenerate the image and placefile in seconds.
Without this, it will only generate once

`verbose`: Print status messages if true

`timeout`: How long to wait for a responce from the URL in seconds. Defaults to
30s. No way to disable, because that will lock up the program

## Other Radar Viewers
If another radar viewer uses a Mercator projection and has placefile support,
this project should work, although I give no guaranties.

## Overview of how `grib2pf` Works
The MRMS grib files provide a grid (in latitude/longitude space) of data. Each
grid point has a value, latitude, and longitude. Every point in a column has
the same longitude, and every point in a row has the same latitude. `grib2pf`
converts the latitudes and longitudes to x,y coordinates on a Mercator
projection. In order to maximize the pixel density of the output image, these
x,y coordinates are normalized such that 0,0 is the top left, and imageWidth -
1,imageHeight - 1 is the bottom left of the grib data (image coordinates). This
is simply a linear transformation of normal Mercator projections, which is
undone when the placefile is rendered because of the latitude and longitude
coordinates saved in the placefile. Then for each column and row in the image,
the nearest column or row in the grib data is found. Although multiple grib
data points are under each pixel, only the nearest is used. Averaging would
require more processing time, because this only needs to touch one grib data
point per pixel. This is also not a huge issue because this is designed simply
to give an overview of national weather, and local radar can provide better
local data. That being said, if someone could create an efficient version of
averaging (probably using numpy or opencv, or some other library), I would be
interested. Then, the value of each point is converted to a color based on the
color file, and the image is saved to disk. The placefile simply has the path
or URL to the image, and the coordinates of the 4 corners of the data.
