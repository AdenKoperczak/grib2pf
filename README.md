# grib2pf
This is a python script which takes GRIB data (mainly MRMS) and outputs it to a
placefile for usage with Supercell-WX. This adds the ability for nation wide
weather radar in Supercell-WX.

## Setup Guide
This installation guide is written for non technical users. More technical
users may want to modify the procedure.

### Python
You will need Python. I developed using Python3.12, but any currently supported
versions of Python should work.

On Linux, download using your package manager (apt, pacman, etc)

On Windows, you can download Python from the Windows Store, using `winget`, or
directly from the Python website (https://www.python.org/downloads/). Make sure
that "py.exe" is on your path as well.

### Downloading the Repository
You can download the repository by pressing the green "Code" button on GitHub,
and selecting Download ZIP. You can also clone the repository using git, if you
prefer. Unzip this in a reasonable location, where you will not accidentally
delete it. The folder will be called the source folder from now on

### Installing Python Dependencies
For Windows, double click on the `setup.bat` to install python dependencies.
For Linux, run the `setup.sh` script. You may need to use a virtual environment
or user level install in order for this to work on Linux.

### Set Settings
Settings are done through a JSON file. Create a file called `settings.json` in
your source folder, and open it with a text editor (such as notepad). Below is
an example settings file for MRMS base reflectivity. Make sure to change the
paths to match your source folder.

```
{
    "url": "https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS_MergedBaseReflectivity.latest.grib2.gz",
    "imageFile": "{source folder}/baseReflectivity.png",
    "placeFile": "{source folder}/baseReflectivity.txt",
    "verbose": true,
    "refresh": 15,
    "regenerateTime": 60
}
```

This basic setup will make a update the placefile every minute. Updating the
placefile is somewhat slow, and the MRMS data is only updated every minute (I
think), so this is often enough. In order to stop it use press CTRL-C in the
terminal it launches.

You can create multiple setting files, and run them concurrently.

### Running
#### run.bat/run.sh
Double clicking run.bat (Windows) or run.sh (Linux) should run the program.
This will only use `settings.json` for the settings.

#### Command Line (Windows)
In File Explorer, while in your source folder, click on the address box, type
`cmd`, and press Enter. This will bring up a command prompt. Copy the following
command into it to start the program
```
py.exe grib2pf.py settings.json
```

#### Shortcut (Windows)
You can create a shortcut, and use the following line as the target to start
the script. Make sure to correctly set the paths.
```
py.exe "{source folder}/grib2pf.py" "{source folder}/settings.json"
```
You can also replace `settings.json` with another file in order to run using a
different product.

### Adding To Supercell-WX
Copy the path to the placefile (`placeFile` in `settings.json`), and use it
as the URL for a placefile in Supercell-WX.

## Settings
Below are all the settings supported by this program.

url: The URL to pull from. Should probably come from
"https://mrms.ncep.noaa.gov/data"
"https://mrms.ncep.noaa.gov/data/2D/MergedBaseReflectivity/MRMS\_MergedBaseReflectivity.latest.grib2.gz"
is a useful reflectivity plot

imageFile: The file name were the image should be written. Should be an
absolute path to a png.

placeFile: The file name were the placefile should be written

palette: The path to a GRS color table to use for this plot. Useful for non
reflectivity plots

title: The title to display in Supercell-WX

refresh: How often Supercell-WX should refresh the placefile, in seconds

imageURL: The URL at which the image will be hosted, Unnecessary for local
usage only

imageWidth: The width of the image to be generated. Only effects the resolution
off the plot

imageHeight: The height of the image to be generated. Only effects the
resolution off the plot

regenerateTime: How often to regenerate the image and placefile in seconds.
Without this, it will only generate it once.

verbose: Print status messages if true

## Other Radar Viewers
If another radar viewer uses a Mercator projection and has placefile support,
this project should work, although I give no guaranties.
