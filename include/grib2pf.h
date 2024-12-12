#ifndef GRIB2PF_H
#define GRIB2PF_H

#include "color_table.h"
#include <stdbool.h>

typedef struct {
    double lonL, lonR, latT, latB;
} OutputCoords;

typedef struct {
    const char* url;
    bool gzipped;
    const char* imageFile;
    const ColorTable* palette;
    size_t imageWidth;
    size_t imageHeight;
    bool verbose;
    uint64_t timeout;
} Settings;

int generate_image(const Settings* settings, OutputCoords* output);

#endif
