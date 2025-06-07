#ifndef GRIB2PF_H
#define GRIB2PF_H

#include "color_table.h"
#include <stdbool.h>

typedef struct {
    double lonL, lonR, latT, latB;
} ImageArea;

typedef enum RenderMode {
    Average_Data = 0,
    Nearest_Data = 1,
    Nearest_Fast_Data = 2,
    Max_Data = 3,
    Min_Data = 4,
} RenderMode;

typedef struct {
    ImageArea topLeftArea;
    ImageArea topRightArea;
    ImageArea bottomLeftArea;
    ImageArea bottomRightArea;
} OutputImageAreas;

typedef struct {
    bool tiled;
    const char* topLeftImageFile;
    const char* topRightImageFile;
    const char* bottomLeftImageFile;
    const char* bottomRightImageFile;

    const ColorTable* palette;
    size_t imageWidth;
    size_t imageHeight;
    const char* title;
    /*RenderMode*/int mode;
    double minimum;
    bool contour;

    bool customArea;
    ImageArea area;

    size_t offset;

    OutputImageAreas output;
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

    bool tiled;
    const char* topLeftImageFile;
    const char* topRightImageFile;
    const char* bottomLeftImageFile;
    const char* bottomRightImageFile;

    const ColorTable* rainPalette;
    const ColorTable* snowPalette;
    const ColorTable* hailPalette;
    double minimum;
    size_t imageWidth;
    size_t imageHeight;
    /*RenderMode*/int mode;

    bool customArea;
    ImageArea area;
} MRMSTypedReflSettings;

#if defined(GRIB2PF_LIBRARY) && defined(_WIN32)
#define GRIB2PF_LIB __declspec(dllexport)
#else
#define GRIB2PF_LIB
#endif

GRIB2PF_LIB int generate_image(const Settings* settings);

GRIB2PF_LIB int generate_mrms_typed_refl(const MRMSTypedReflSettings* settings,
                             OutputImageAreas* output);
#endif
