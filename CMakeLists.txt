cmake_minimum_required(VERSION 3.21)
set(PROJECT_NAME grib2pf)
project(${PROJECT_NAME}
        VERSION      0.1.0
        DESCRIPTION  "Convert GRIB2 (MRMS) files to placefiles for Supercell Wx"
        HOMEPAGE_URL "https://github.com/adenkoperczak/grib2pf"
        LANGUAGES    C)

find_package(PNG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(CURL REQUIRED)

set(ENABLE_FORTRAN OFF CACHE BOOL "")
set(ENABLE_NETCDF OFF CACHE BOOL "")
set(ENABLE_JPG ON CACHE BOOL "")
set(ENABLE_AEC OFF CACHE BOOL "")
set(ENABLE_PNG ON CACHE BOOL "")
set(IEEE_LE "1" CACHE STRING "")
set(ENABLE_MEMFS ON CACHE BOOL "")
set(ENABLE_EXTRA_TESTS OFF CACHE BOOL "")
set(BUILD_TOOLS OFF CACHE BOOL "")

add_subdirectory(eccodes)

set(app_SRCS source/grib2pf.c source/color_table.c)
include_directories(grib2pf PRIVATE include)

#add_executable(grib2pf ${app_SRCS})
add_library(grib2pf ${app_SRCS})
target_link_libraries(grib2pf PUBLIC PNG::PNG
                                     eccodes
                                     ZLIB::ZLIB
                                     CURL::libcurl)
set_property(TARGET grib2pf PROPERTY C_STANDARD 11)
