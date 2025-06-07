# grib2pf
This is a python script and C code which takes GRIB data (mainly MRMS) and
outputs it to a placefile for usage with Supercell-Wx. This adds the ability
for nation wide weather radar in Supercell-Wx.

## Update Guide Windows
There are 2 ways to update this on Windows. The second way is will allways work
but takes a bit more effort. The first ways is simpler

### Simple Update
Unzip the new `grib2pf` folder from the zip overtop your preexisting folder,
and select "Replace the files in the destination". This will save your settings.

### Complete Update
1. Go into the `grib2pf` folder, then the `_internal` folder.
2. Copy `settings.jsonc` or `settings` to your Desktop, or somewhere outside of
   the `grib2pf` folder.
3. Delete the `grib2pf` folder.
4. Unzip the new `grib2pf` folder where you want it.
4. Move the `settings.jsonc` or `settings` file back into the `_internal` folder
   inside the `grib2pf` folder.

## Setup Guide Windows
There are 2 main ways to run this in Windows: WSL or via an executable. For
WSL follow the Linux instructions. These instructions are for the executable.

### Windows Dependencies
You will need the latest Microsoft Visual C++ Runtime to run this program. If
you have Supercell-Wx v4.5.0 running on your system, then you should already
have them. Otherwise download them from
https://aka.ms/vs/17/release/vc_redist.x64.exe .

### Download The Executable
Download the executable form the latest release and extract it. You will want
to extract it to a permanent location. This program does not install itself, so
where you place it is where it will be installed.

### Running the GUI
`grib2pf-ui.exe` or `grib2pf-ui` can be run by double clicking it. This will
launch a settings UI. You can select a preset to start with by clicking `Load
Preset`. From there you can modify the settings to your liking. Clicking `Run`
will save your settings and run `grib2pf`. Once your settings are saved, you
can simply run `grib2pf` directly, without the GUI.

### Run It
For a basic run, you can simply double click on `grib2pf.exe` or `grib2pf`.
This will put a basic settings file (`settings.json`) in the `_internal` folder.
It should look like below, where `{_internal folder}` is replaced by the path
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
git submodule update --init --recursive
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
cd ..
pip install -r requirements.txt
```
You can then run `grib2pf.py` and `grib2pf-ui.py` as normal scripts.

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

## Contours
Contours are an optional feature which can be used to help see how data is
changing over distance. It is similar in concept to isotherms. Each color table
entry is given a contour. Only the pixels that are determined to be contour are
rendered. They have their initial value, so the color table can define the color
of given contours. Below is an example color table that can be used with Kelvin
based temperature data. It covers -30 to 40 degrees Celsius, with a contour
every 10 degrees.

```placefile
offset: -273

Color: -30   0   0   0
Color: -20   0   0 255
Color: -10   0 255 255
Color:   0   0 255   0
Color:  10 255 255   0
Color:  20 255   0   0
Color:  30 255   0 255
Color:  40 255 255 255
```

## Arguments
When run without an argument, `grib2pf` will run using the settings file in the
install directory (`grib2pf` on Linux, and `grib2pf\_internal` on Windows).
When run with one argument, `grib2pf` will use that argument as the path to a
settings file. Otherwise, `grib2pf` can be run without a settings file, using
arguments instead. The arguments documentation can be seen by running `grib2pf`
with `--help`. The arguments align with the settings described below.

## Other Radar Viewers
If another radar viewer uses a Mercator projection and has placefile support,
this project should work, although I give no guaranties.

## Overview of how `grib2pf` Works
The grib2 files provide a grid (in a variable coordinate space) of data. Each
grid point has a value, latitude, and longitude. `grib2pf` converts the
latitudes and longitudes to x,y coordinates on a Mercator projection. In order
to maximize the pixel density of the output image, these x,y coordinates are
normalized such that 0,0 is the top left, and imageWidth - 1,imageHeight - 1 is
the bottom right of the grib data (image coordinates). This is simply a linear
transformation of normal Mercator projections, which is undone when the
placefile is rendered because of the latitude and longitude coordinates saved
in the placefile. The pixels values are determined in several modes depending
on `renderMode`. `Average_Data` averages the data under the pixel.
`Nearest_Data` and `Nearest_Fast_Data` find the nearest data point to the
center of the pixel (`Nearest_Data` should be used if the resolution of the
image is higher than the resolution of the data. AKA if you are seeing holes in
the data). `Max_Data` uses the largest value under the pixel. `Min_Data` uses
the smallest value under the pixel.
