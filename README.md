# grib2pf
This is a python script which takes GRIB data (mainly MRMS) and outputs it to a
placefile for usage with Supercell-WX. This adds the ability for nation wide
weather radar in Supercell-WX.

## Setup Guide
This installation guide is written for non technical users. More technical
users may want to modify the procedure.


### Setting Up WSL
Unfortunately, all Python libraries I can find only work under Linux and MacOS.
Fortunately, windows now includes Windows Subsystem for Linux (WSL) which makes
installing the needed libraries possible, although somewhat complicated.

I recommend following the guide at
(https://learn.microsoft.com/en-us/windows/wsl/install). There is no need to
change the default Linux distro, as the rest of this guide assumes you are
using Ubuntu.

### Linux Shell Basics
You can launch the Ubuntu WSL from the start menu, or by pressing the Windows
key and searching for Ubuntu. This will launch a Linux shell/command
line/terminal. It looks intimidating at first, but it gets easier as you work
with it. Lets start with some basic commands. You start in your Linux home
folder. To list files in it, type `ls`. To start with you will not have any
files there. Next we can use `cd` to change directories (directories are the
same as folders). Type the following, replacing "{User}" with your Windows
username.
```
cd /mnt/c/Users/{User}/Desktop
```
This will move you to your Windows desktop. Use `ls` to view the files on your
desktop. You will notice that Linux uses `/` in paths, unlike Windows which
uses `\`. You may also notice that `/mnt/c/Users/{User}/Desktop` looks awfully
similar to `C:\Users\{User}\Desktop`. This should give you a good idea on how
to navigate your Windows files. Now use `cd ..`. This moves you up one
directory to `/mnt/c/Users/{User}`. Now you can run `cd Downloads` to move into
your Downloads folder.

On Linux, you usually install software using a package manager, not by
downloading from the internet. On Ubuntu we will be using `apt` to install
the needed packages (software). This will also require the usage of the `sudo`
(SuperUser DO) command. This lets you run a program as root/admin.

### Installing Needed Packages
For this program you will need a few packages. The below command will ensure
you have all the packages you need. (python3 is the programming language this
is written in. python3-pip is a package manager for python, git lets you pull
code from GitHub.)
```
sudo apt install python3 python3-pip git
```

### Cloning the repo
Navigate to a location where you want to install this program. Then use the
following command to clone (download) the repository for GitHub. This will
create a `grib2pf` folder.
```
git clone https://github.com/AdenKoperczak/grib2pf.git
```
Next `cd` into `grib2pf`. This is now refered to as the source folder.

To update this code you can simply use `git pull`.

### Running the setup script.
Simply type `./setup.sh` to run the setup script. This installs needed Python
dependencies, and creates a basic `settings.json`

### Set Settings
Settings are done through a JSON file. The setup script created a file called
`settings.json` in your source folder. You can open it with a text editor
(such as Notepad). It should look something like below.

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

This basic setup will update the placefile every minute. Updating the placefile
is somewhat slow, and the MRMS data is only updated every other minute, so
this is should be enough. In order to stop it use press CTRL-C in the terminal
it launches.

You can create multiple setting files, and run them concurrently.

### Running
#### run.sh
From the Linux shell, type `./run.sh` while in your source directory.

#### From The Shell Directly
The below command lets you run it directly from your Shell. By changing
`settings.json` you can use diffrent settings files.
```
python3 grib2pf.py settings.json
```

### Adding To Supercell-WX
Copy the path to the placefile, and use it as the URL for a placefile in
Supercell-WX. Because Supercell-WX is running under Windows, you need to use
the Windows path to the placefile.

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
reflectivity plots

`title`: The title to display in Supercell-WX

`refresh`: How often Supercell-WX should refresh the placefile, in seconds

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
