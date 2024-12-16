#ifndef GRIB2PF_H
#define GRIB2PF_H

#include "color_table.h"
#include <stdbool.h>

typedef struct {
    double lonL, lonR, latT, latB;
} OutputCoords;

typedef enum RenderMode {
    Average_Data = 0,
    Nearest_Data = 1,
    Nearest_Fast_Data = 2,
} RenderMode;

typedef struct {
    const char* imageFile;
    const ColorTable* palette;
    size_t imageWidth;
    size_t imageHeight;
    const char* title;
    /*RenderMode*/int mode;

    size_t offset;
} MessageSettings;

typedef struct {
    const char* url;
    bool gzipped;
    uint64_t timeout;
    const char* logName;
    bool verbose;

    size_t messageCount;
    MessageSettings* messages;
} Settings;

typedef struct {
    const char* typeUrl;
    const char* reflUrl;
    uint64_t timeout;
    const char* title;
    bool verbose;
    bool gzipped;

    const char* imageFile;
    const ColorTable* rainPalette;
    const ColorTable* snowPalette;
    const ColorTable* hailPalette;
    size_t imageWidth;
    size_t imageHeight;
    /*RenderMode*/int mode;
} MRMSTypedReflSettings;

#if defined(GRIB2PF_LIBRARY) && defined(_WIN32)
#define GRIB2PF_LIB __declspec(dllexport)
#else
#define GRIB2PF_LIB
#endif

GRIB2PF_LIB int generate_image(const Settings* settings, OutputCoords* output);

GRIB2PF_LIB int generate_mrms_typed_refl(const MRMSTypedReflSettings* settings,
                             OutputCoords* output);

#endif
