#!/bin/bash
# Given base.png and base32.png, makes the various sizes of icons needed for
# OS X and Windows, and puts them into .icns and .ico files, respectively.
# To run this script, make sure you have png2icns (icnsutils), and imagemagick
# installed. On Debian, that means you should run:
#     sudo aptitude install icnsutils imagemagick
# This script should be run before running build.py in the parent directory, but
# it only needs to be run when or if the icon(s) changes.

ICON_BASE=base.png     # We have a large pre-rendered icon, and then
ICON_BASE48=base48.png # some smaller ones, because if we just scale the them
ICON_BASE32=base32.png # down from the large one, things get blurry.
ICON_BASE16=base16.png # The rendering is done manually in Inkscape.

function icon_convert {
    convert $1 -resize $2x$2 -gravity center -background transparent \
               -extent $2x$2 $3
}

echo "Setting Up"
rm -rf osx_icon win_icon
mkdir -p osx_icon win_icon

echo "Rescaling and Copying OS X Icons"
icon_convert $ICON_BASE   512 osx_icon/icn512.png
icon_convert $ICON_BASE   256 osx_icon/icn256.png
icon_convert $ICON_BASE   128 osx_icon/icn128.png
icon_convert $ICON_BASE48 48  osx_icon/icn48.png
icon_convert $ICON_BASE32 32  osx_icon/icn32.png
icon_convert $ICON_BASE16 16  osx_icon/icn16.png

echo "Building OS X .icns File"
png2icns osx_icon/icon.icns osx_icon/*.png > /dev/null # quiet, you!


echo "Rescaling and Converting Windows Icons"                                
icon_convert $ICON_BASE   256 win_icon/icn256.bmp
icon_convert $ICON_BASE48 48  win_icon/icn48.bmp
icon_convert $ICON_BASE32 32  win_icon/icn32.bmp
icon_convert $ICON_BASE16 16  win_icon/icn16.bmp

echo "Building Windows .ico File"
convert win_icon/*.bmp win_icon/icon.ico


echo "Cleaning Up"
rm osx_icon/*.png win_icon/*.bmp
