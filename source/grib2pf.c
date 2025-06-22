#define _USE_MATH_DEFINES
#define GRIB2PF_LIBRARY
#include "grib2pf.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#include "png.h"
#include "eccodes.h"
#include "zlib.h"
#include "curl/curl.h"
#include "color_table.h"

#define TIMEFMT "%Y-%m-%d %H:%M:%S"

const double MERCADER_COEF = M_PI / 360;
const double MERCADER_OFFS = M_PI / 4;

#define PROJECT_LAT_Y(lat) log(tan(MERCADER_OFFS + lat * MERCADER_COEF))

#define ARRAY_INIT 10

typedef struct {
    size_t size;
    size_t current;
    uint8_t* data;
} DataBuffer;

typedef struct {
    z_stream strm;
    DataBuffer out;
    bool gzipped;
    bool finished;
} DownloadingData;

typedef struct {
    bool verbose;
    const char* logName;
} LogSettings;

#ifdef _WIN32
#include <sys\timeb.h>
void _log(const LogSettings* settings, char* message) {
    if (!settings->verbose) {
        return;
    }
    struct __timeb64 ts;
    _ftime64(&ts);
    time_t tm = time(NULL);
    int32_t frac = ts.millitm;

    char buffer[24];
    if(strftime(buffer, sizeof(buffer), TIMEFMT, localtime(&tm)) == 0) {
        buffer[0] = '\0';
    }

    printf("[%s.%03d] [%s] %s\n", buffer, frac, settings->logName, message);
}
#else
void _log(const LogSettings* settings, char* message) {
    if (!settings->verbose) {
        return;
    }
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    time_t tm = time(NULL);
    int32_t frac = ts.tv_nsec / 1000000;

    char buffer[24];
    if(strftime(buffer, sizeof(buffer), TIMEFMT, localtime(&tm)) == 0) {
        buffer[0] = '\0';
    }

    printf("[%s.%03d] [%s] %s\n", buffer, frac, settings->logName, message);
}
#endif

#define CHUNCK_SIZE (4 * (1<<20))
#define CHUNCK_PAD  1024

void print_keys(codes_handle* h) {
    codes_keys_iterator* keys = codes_keys_iterator_new(h, 0, "");
    while (codes_keys_iterator_next(keys)) {
        printf("%s\n", codes_keys_iterator_get_name(keys));
    }
}

size_t chunk_from_server(void *contents, size_t size, size_t nmemb, void *userp) {
    DownloadingData* data = userp;
    size_t inputSize = size * nmemb;

    LogSettings log = {.verbose = true, .logName = "test" };

    if (inputSize == 0) {
        fprintf(stderr, "Got empty response from the server\n");
        return 0;
    }

    if (data->finished) {
        fprintf(stderr, "Got more data after finished inflating\n");
    }

    if (data->gzipped) {
        data->strm.next_in  = contents;
        data->strm.avail_in = inputSize;

        while (data->strm.avail_in > 0) {
            if (data->strm.avail_out < CHUNCK_PAD) {
                uint8_t* ptr = realloc(data->out.data, data->out.size + CHUNCK_SIZE);
                if (ptr == NULL) {
                    fprintf(stderr, "Could not allocate buffer\n");
                    return CURL_WRITEFUNC_ERROR;

                }
                data->out.data       = ptr;
                data->out.size       += CHUNCK_SIZE;
                data->strm.next_out  = ptr + data->strm.total_out;
                data->strm.avail_out += CHUNCK_SIZE;
            }

            int err = inflate(&(data->strm), Z_NO_FLUSH);
            switch(err) {
            case Z_OK:
                break;
            case Z_STREAM_END:
                data->finished = true;
                break;

            default:
                fprintf(stderr, "Got %s while inflating\n%s\n", zError(err),
                        data->strm.msg == NULL ? "" : data->strm.msg);
                return CURL_WRITEFUNC_ERROR;
            }
        }
    } else {
        while (data->out.size - data->out.current < inputSize) {
            size_t newSize;
            if (data->out.size == 0) {
                newSize = CHUNCK_SIZE;
            } else {
                newSize = data->out.size * 2;
            }
            uint8_t* ptr = realloc(data->out.data, newSize);
            if (ptr == NULL) {
                fprintf(stderr, "Could not allocate buffer\n");
                return CURL_WRITEFUNC_ERROR;

            }
            data->out.data = ptr;
            data->out.size = newSize;
        }
        memcpy(data->out.data + data->out.current, contents, inputSize);
        data->out.current += inputSize;
    }


    return inputSize;
}

typedef struct {
    bool verbose;
    const char* logName;
    bool gzipped;
    const char* url;
    uint64_t timeout;
} DownloadSettings;

typedef struct {
    size_t totalSize;
    uint8_t* gribStart;
    uint8_t* data;
    int error;
} DownloadedData;

DownloadedData download_data(const DownloadSettings* settings) {
    DownloadedData output;
    output.error = 0;

    int err;
    size_t totalSize;
    LogSettings logS = {
        .verbose = settings->verbose,
        .logName = settings->logName,
    };
    CURL* curl = NULL;
    CURLcode res;

    DownloadingData data;
    data.finished = false;

    data.out.size = 0;
    data.out.data = NULL;
    data.out.current = 0;

    data.strm.zalloc    = Z_NULL;
    data.strm.zfree     = Z_NULL;
    data.strm.opaque    = Z_NULL;
    data.strm.next_in   = NULL;
    data.strm.avail_in  = 0;
    data.strm.next_out  = NULL;
    data.strm.avail_out = 0;

    data.gzipped = settings->gzipped;

    _log(&logS, "Downloading");
    err = inflateInit2(&(data.strm), 15 + 16);
    if (err != Z_OK) {
        fprintf(stderr, "Could not initialize zlib stream\n");
        output.error = 1;
        return output;
    }

    curl = curl_easy_init();
    if (curl == NULL) {
        fprintf(stderr, "Could not initialize curl\n");
        output.error = 1;
        return output;
    }
    curl_easy_setopt(curl, CURLOPT_URL, settings->url);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, settings->timeout);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, chunk_from_server);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, true);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &data);

    res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        fprintf(stderr, "Failed to get URL %s with: %s\n", settings->url,
                curl_easy_strerror(res));
        output.error = 1;
        return output;
    }
    curl_easy_cleanup(curl);
    if (settings->gzipped) {
        totalSize = data.strm.total_out;
    } else {
        totalSize = data.out.current;
    }
    inflateEnd(&(data.strm));


    uint8_t* d = data.out.data;
    {
        size_t i = 4;
        while (i < totalSize) {
            if (memcmp(d, "GRIB", 4) == 0) {
                break;
            }
            d++;
            i++;
        }
        totalSize = totalSize + 4 - i;
    }

    output.totalSize = totalSize;
    output.gribStart = d;
    output.data      = data.out.data;

    return output;
}

typedef struct {
    ImageArea coords;
    double* imageData;
    uint32_t* counts;
    int error;
} ImageData;

double correct_alias(double a, double b) {
    // Find the "alias number" for a and b
    double Na = floor((a - 180) / 360) + 1;
    double Nb = floor((b - 180) / 360) + 1;

    // make b be on the same alias as a
    return b + (Na - Nb) * 360;
}

ImageData generate_image_data(MessageSettings* message, uint8_t* d, size_t size,
                            bool verbose, size_t* offsets, size_t offsetsSize) {
    ImageData output;
    output.error = 0;

    LogSettings logS = {
        .verbose = verbose,
        .logName = message->title,
    };
    size_t offset = message->offset;
    if (offsetsSize > 0 && offsets != NULL) {
        if (offsetsSize <= offset) {
            output.error = 1;
            return output;
        }
        offset = offsets[offset];
    }

    codes_handle* h = codes_handle_new_from_message(NULL, d + offset,
            size - offset);
    if (h == NULL) {
        fprintf(stderr, "Could not read in product\n");
        output.error = 1;
        return output;
    }

    _log(&logS, "Preparing Data");

    size_t latLonValuesSize;
    double* latLonValues;
    CODES_CHECK(codes_get_size(h, "latLonValues", &latLonValuesSize), 0);
    latLonValues = malloc(latLonValuesSize * sizeof(double));
    if (latLonValues == NULL) {
        output.error = 1;
        return output;
    }
    CODES_CHECK(codes_get_double_array(h, "latLonValues",
                latLonValues, &latLonValuesSize), 0);
    codes_handle_delete(h);

    double lonL, lonR, latT, latB;
    lonL = 1000;
    lonR = -1000;
    latB = 1000;
    latT = -1000;

    for (size_t i = 0; i < latLonValuesSize; i += 3) {
        const double lat = latLonValues[i + 0];
        const double lon = latLonValues[i + 1];
        if (lon > lonR)
            lonR = lon;
        if (lon < lonL)
            lonL = lon;
        if (lat > latT)
            latT = lat;
        if (lat < latB)
            latB = lat;
    }

    if (message->customArea) {
        // correct aliasing. Includes logic for crossing the anti-meridian
        double lonRL = correct_alias(lonL, message->area.lonR);
        double lonRR = correct_alias(lonR, message->area.lonR);
        double newLonR;
        if (lonL < lonRL && lonRL < lonR) {
            newLonR = lonRL;
        } else {
            newLonR = lonRR;
        }

        double lonLL = correct_alias(lonL, message->area.lonL);
        double lonLR = correct_alias(lonR, message->area.lonL);
        double newLonL;
        if (lonL < lonLR && lonRL < lonR) {
            newLonL = lonLR;
        } else {
            newLonL = lonLL;
        }

        lonR = newLonR;
        lonL = newLonL;
        latT = message->area.latT;
        latB = message->area.latB;
    }

    output.coords.lonL = lonL;
    output.coords.lonR = lonR;
    output.coords.latT = latT;
    output.coords.latB = latB;

    const double xM = (message->imageWidth - 0.01)  / (lonR - lonL);
    const double yM = (message->imageHeight - 0.01) / (PROJECT_LAT_Y(latB) - PROJECT_LAT_Y(latT));
    const double yB = PROJECT_LAT_Y(latT);

    double* imageData = NULL;
    uint32_t* counts   = NULL;
    imageData = calloc(message->imageWidth * message->imageHeight, sizeof(*imageData));
    counts    = calloc(message->imageWidth * message->imageHeight, sizeof(*counts));
    if (imageData == NULL || counts == NULL) {
        output.error = 1;
        return output;
    }

    output.imageData = imageData;
    output.counts = counts;

    double lastLat = -10000;
    double lastY   = 0;

    switch (message->mode) {
    case Average_Data: {
        for (size_t i = 0; i < latLonValuesSize; i += 3) {
            double lat   = latLonValues[i + 0];
            double lon   = latLonValues[i + 1];
            double value = latLonValues[i + 2];

            if (value < message->minimum) {
                continue;
            }

            double x = (lon - lonL) * xM;
            double y;
            if (lat == lastLat) {
                y = lastY;
            } else {
                y = (PROJECT_LAT_Y(lat) - yB) * yM;
                lastLat = lat;
                lastY   = y;
            }

            if (x < 0 || y < 0 ||
                    x >= message->imageWidth || y >= message->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * message->imageWidth;

            imageData[index] += value;
            counts[index]    += 1;
        }
        break; }
    case Nearest_Data: {
        double* nearestDist = malloc(message->imageWidth * message->imageHeight * sizeof(*nearestDist));
        if (nearestDist == NULL) {
            output.error = 1;
            return output;
        }
        for (size_t i = 0; i < message->imageWidth * message->imageHeight; i++) {
            nearestDist[i] = 1000000;
        }
        for (size_t i = 0; i < latLonValuesSize; i += 3) {
            double lat   = latLonValues[i + 0];
            double lon   = latLonValues[i + 1];
            double value = latLonValues[i + 2];

            if (value < message->minimum) {
                continue;
            }

            double x = (lon - lonL) * xM;
            double y;
            if (lat == lastLat) {
                y = lastY;
            } else {
                y = (PROJECT_LAT_Y(lat) - yB) * yM;
                lastLat = lat;
                lastY   = y;
            }

            if (x < 0 || y < 0 ||
                    x >= message->imageWidth || y >= message->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;

            size_t index;
            double dx;
            double dy;
            double dist;

            #define DO_NEAREST_FOR_POINT(DX, DY) {                      \
                index = iX + DX + (iY + DY) * message->imageWidth;      \
                dx = (x - (iX + DX + 0.5));                             \
                dy = (y - (iY + DY + 0.5));                             \
                dist = dx * dx + dy * dy;                               \
                if (nearestDist[index] > dist) {                        \
                    imageData[index]   = value;                         \
                    counts[index]      = 1;                             \
                    nearestDist[index] = dist;                          \
                }}

            DO_NEAREST_FOR_POINT(0, 0);
            if (iX >= 1) DO_NEAREST_FOR_POINT(-1, 0);
            if (iY >= 1) DO_NEAREST_FOR_POINT(0, -1);
            if (iX >= 1 && iY >= 1) DO_NEAREST_FOR_POINT(-1, -1);
            if (iX < message->imageWidth - 1) DO_NEAREST_FOR_POINT(1, 0);
            if (iY < message->imageHeight - 1) DO_NEAREST_FOR_POINT(0, 1);
            if (iX < message->imageWidth - 1 && iY < message->imageHeight - 1)
                DO_NEAREST_FOR_POINT(1, 1);
            if (iX >= 1 && iY < message->imageHeight - 1)
                DO_NEAREST_FOR_POINT(-1, 1);
            if (iX < message->imageWidth - 1 && iY >= 1)
                DO_NEAREST_FOR_POINT(1, -1);
        }
        free(nearestDist);
        break; }
    case Nearest_Fast_Data: {
        double* nearestDist = malloc(message->imageWidth * message->imageHeight * sizeof(*nearestDist));
        if (nearestDist == NULL) {
            output.error = 1;
            return output;
        }
        for (size_t i = 0; i < message->imageWidth * message->imageHeight; i++) {
            nearestDist[i] = 3; // distances should be <= 2
        }
        for (size_t i = 0; i < latLonValuesSize; i += 3) {
            double lat   = latLonValues[i + 0];
            double lon   = latLonValues[i + 1];
            double value = latLonValues[i + 2];

            if (value < message->minimum) {
                continue;
            }

            double x = (lon - lonL) * xM;
            double y;
            if (lat == lastLat) {
                y = lastY;
            } else {
                y = (PROJECT_LAT_Y(lat) - yB) * yM;
                lastLat = lat;
                lastY   = y;
            }

            if (x < 0 || y < 0 ||
                    x >= message->imageWidth || y >= message->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * message->imageWidth;

            double dx = (x - (iX + 0.5));
            double dy = (y - (iY + 0.5));
            double dist = dx * dx + dy * dy;

            if (nearestDist[index] > dist) {
                imageData[index]   = value;
                counts[index]      = 1;
                nearestDist[index] = dist;
            }
        }
        free(nearestDist);
        break; }
    case Max_Data: {
        for (size_t i = 0; i < latLonValuesSize; i += 3) {
            double lat   = latLonValues[i + 0];
            double lon   = latLonValues[i + 1];
            double value = latLonValues[i + 2];

            if (value < message->minimum) {
                continue;
            }

            double x = (lon - lonL) * xM;
            double y;
            if (lat == lastLat) {
                y = lastY;
            } else {
                y = (PROJECT_LAT_Y(lat) - yB) * yM;
                lastLat = lat;
                lastY   = y;
            }

            if (x < 0 || y < 0 ||
                    x >= message->imageWidth || y >= message->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * message->imageWidth;

            if (imageData[index] < value || counts[index] == 0) {
                imageData[index]   = value;
                counts[index]      = 1;
            }
        }

        break; }
    case Min_Data: {
        for (size_t i = 0; i < latLonValuesSize; i += 3) {
            double lat   = latLonValues[i + 0];
            double lon   = latLonValues[i + 1];
            double value = latLonValues[i + 2];

            if (value < message->minimum) {
                continue;
            }

            double x = (lon - lonL) * xM;
            double y;
            if (lat == lastLat) {
                y = lastY;
            } else {
                y = (PROJECT_LAT_Y(lat) - yB) * yM;
                lastLat = lat;
                lastY   = y;
            }

            if (x < 0 || y < 0 ||
                    x >= message->imageWidth || y >= message->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * message->imageWidth;

            if (imageData[index] > value || counts[index] == 0) {
                imageData[index]   = value;
                counts[index]      = 1;
            }
        }

        break; }
    }
    free(latLonValues);

    return output;
}

void contour_image_data(MessageSettings* message, ImageData* input) {

    // This is somewhat inefficent right now. It would be faster to go over the
    // data twice, once to label, and again to contour
    for (size_t x = 0; x < message->imageWidth - 1; x++) {
        for (size_t y = 0; y < message->imageHeight - 1; y++) {
            size_t is[4];
            double values[4];
            ssize_t indexes[4];
#define GET_INDEX(index, xoff, yoff) { \
                is[index] = (x + xoff) + (y + yoff) * message->imageWidth; \
                if (input->counts[is[index]] == 0) { \
                    values[index] = 0; \
                    indexes[index] = -1; \
                } else { \
                    values[index] = input->imageData[is[index]] / input->counts[is[index]]; \
                    indexes[index] = color_table_get_index(message->palette, values[index]); \
                } \
            }
            GET_INDEX(0, 0, 0)
            GET_INDEX(1, 1, 0)
            GET_INDEX(2, 0, 1)
            GET_INDEX(3, 1, 1)
#undef GET_INDEX

            if (indexes[0] == indexes[1] &&
                indexes[0] == indexes[2] &&
                indexes[0] == indexes[3]) {
                input->counts[is[0]] = 0;
            }
        }
    }

    for (size_t x = 0; x < message->imageWidth; x++) {
        size_t i = x + (message->imageHeight - 1) * message->imageWidth;
        input->counts[i] = 0;
    }
    for (size_t y = 0; y < message->imageHeight; y++) {
        size_t i = (message->imageWidth - 1) + (y) * message->imageWidth;
        input->counts[i] = 0;
    }
}


int save_image(MessageSettings* message,
               ImageData* imData,
               uint8_t* imageBuffer) {
    if (message->tiled) {
        size_t leftWidth    = message->imageWidth / 2;
        size_t rightWidth   = message->imageWidth - leftWidth;
        size_t topHeight    = message->imageHeight / 2;
        size_t bottomHeight = message->imageHeight - topHeight;

        png_image image;

        memset(&image, 0, sizeof(image));
        image.version = PNG_IMAGE_VERSION;
        image.format = PNG_FORMAT_RGBA;
        image.width  = rightWidth; // rightWidth >= leftWidth
        image.height = bottomHeight; // bottomHeight >= topHeight
        image.flags = 0;
        uint8_t* tileBuffer = malloc(PNG_IMAGE_SIZE(image));
        if (tileBuffer == NULL) {
            return 1;
        }
        png_image_free(&image);

#define WRITE_TILE(WIDTH, HEIGHT, X_OFFSET, Y_OFFSET, PATH)                         \
        memset(&image, 0, sizeof(image));                                           \
        image.version = PNG_IMAGE_VERSION;                                          \
        image.format = PNG_FORMAT_RGBA;                                             \
        image.width  = WIDTH;                                                       \
        image.height = HEIGHT;                                                      \
        image.flags = 0;                                                            \
        for (size_t y = 0; y < HEIGHT; y++) {                                       \
            size_t inputI  = ((Y_OFFSET + y) * message->imageWidth + X_OFFSET) * 4; \
            size_t outputI = y * WIDTH * 4;                                         \
            memcpy(tileBuffer + outputI, imageBuffer + inputI, WIDTH * 4);          \
        }                                                                           \
        if (png_image_write_to_file(&image,                                         \
                                    PATH,                                           \
                                    0,                                              \
                                    tileBuffer,                                     \
                                    0,                                              \
                                    NULL) == 0) {                                   \
            fprintf(stderr, "Did not write image\n");                               \
        }                                                                           \
        png_image_free(&image);

        WRITE_TILE(leftWidth,  topHeight,    0,         0,         message->topLeftImageFile);
        WRITE_TILE(rightWidth, topHeight,    leftWidth, 0,         message->topRightImageFile);
        WRITE_TILE(leftWidth,  bottomHeight, 0,         topHeight, message->bottomLeftImageFile);
        WRITE_TILE(rightWidth, bottomHeight, leftWidth, topHeight, message->bottomRightImageFile);
#undef WRITE_TILE
        free(tileBuffer);

        // find middle coords
        double coef;
        double cordDiff;

        coef     = ((double)leftWidth) / ((double)message->imageWidth);
        cordDiff = imData->coords.lonR - imData->coords.lonL;
        double middleLon = imData->coords.lonL + coef * cordDiff;

        const double yM = (message->imageHeight - 0.01) / (PROJECT_LAT_Y(imData->coords.latB) - PROJECT_LAT_Y(imData->coords.latT));
        const double yB = PROJECT_LAT_Y(imData->coords.latT);
        double dy = ((double)topHeight) / yM + yB;
        double middleLat = (atan(exp(dy)) - MERCADER_OFFS) / MERCADER_COEF;

        message->output.topLeftArea.latT = imData->coords.latT;
        message->output.topLeftArea.latB = middleLat;
        message->output.topLeftArea.lonL = imData->coords.lonL;
        message->output.topLeftArea.lonR = middleLon;

        message->output.topRightArea.latT = imData->coords.latT;
        message->output.topRightArea.latB = middleLat;
        message->output.topRightArea.lonL = middleLon;
        message->output.topRightArea.lonR = imData->coords.lonR;

        message->output.bottomLeftArea.latT = middleLat;
        message->output.bottomLeftArea.latB = imData->coords.latB;
        message->output.bottomLeftArea.lonL = imData->coords.lonL;
        message->output.bottomLeftArea.lonR = middleLon;

        message->output.bottomRightArea.latT = middleLat;
        message->output.bottomRightArea.latB = imData->coords.latB;
        message->output.bottomRightArea.lonL = middleLon;
        message->output.bottomRightArea.lonR = imData->coords.lonR;

        return 0;
    } else {
        png_image image;
        memset(&image, 0, sizeof(image));
        image.version = PNG_IMAGE_VERSION;
        image.format = PNG_FORMAT_RGBA;
        image.width  = message->imageWidth;
        image.height = message->imageHeight;
        image.flags = 0;

        if (png_image_write_to_file(&image,
                                    message->topLeftImageFile,
                                    0,
                                    imageBuffer,
                                    0,
                                    NULL) == 0) {
            return 1;
        }
        png_image_free(&image);

        message->output.topLeftArea.latT = imData->coords.latT;
        message->output.topLeftArea.latB = imData->coords.latB;
        message->output.topLeftArea.lonL = imData->coords.lonL;
        message->output.topLeftArea.lonR = imData->coords.lonR;

        return 0;
    }
}

int generate_image(const Settings* settings) {
    int err = 0;

    LogSettings logS = {
        .verbose = settings->verbose,
        .logName = settings->logName,
    };
    DownloadSettings downloadS = {
        .verbose = settings->verbose,
        .logName = settings->logName,
        .gzipped = settings->gzipped,
        .url     = settings->url,
        .timeout = settings->timeout,
    };
    DownloadedData data = download_data(&downloadS);

    size_t* offsets = NULL;
    size_t offsetsSize = 0;
    if (settings->calcOffsets) {
        size_t offset = 0;
        size_t offsetsAlloced = ARRAY_INIT;
        offsets = calloc(ARRAY_INIT, sizeof(*offsets));
        if (offsets == NULL) {
            return 1;
        }
        while (offset < data.totalSize) {
            if (offsetsAlloced <= offsetsSize) {
                offsetsAlloced *= 2;
                size_t* new = realloc(offsets, offsetsAlloced * sizeof(*offsets));
                if (new == NULL) {
                    return 1;
                }
                offsets = new;
            }

            offsets[offsetsSize] = offset;
            codes_handle* h = codes_handle_new_from_message(NULL,
                    data.gribStart + offset, data.totalSize - offset);
            if (!h) {
                break;
            }
            size_t msgLen = 0;
            GRIB_CHECK(codes_get_long(h, "totalLength", &msgLen), 0);
            offset += msgLen;
            offsetsSize += 1;
            codes_handle_delete(h);
        }
        printf("%zu\n", offsetsSize);
    }

    for (size_t messageIndex = 0; messageIndex < settings->messageCount;
            messageIndex++) {
        MessageSettings* message = settings->messages + messageIndex;
        ImageData imData = generate_image_data(message, data.gribStart,
                data.totalSize, settings->verbose, offsets, offsetsSize);

        logS.logName = message->title;
        if (imData.error) {
            continue;
        }

        // Contour data if needed
        if (message->contour) {
            _log(&logS, "Contouring Image");
            contour_image_data(message, &imData);
        }

        double*   imageData = imData.imageData;
        uint32_t* counts    = imData.counts;

        _log(&logS, "Rendering Image");

        png_image image;
        memset(&image, 0, sizeof(image));
        image.version = PNG_IMAGE_VERSION;
        image.format = PNG_FORMAT_RGBA;
        image.width  = message->imageWidth;
        image.height = message->imageHeight;
        image.flags = 0;

        uint8_t* imageBuffer = NULL;
        imageBuffer = malloc(PNG_IMAGE_SIZE(image));
        if (imageBuffer == NULL) {
            return 1;
        }
        png_image_free(&image);
        for (size_t i = 0; i < message->imageWidth * message->imageHeight; i++) {
            if (counts[i] == 0) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else {
                double value = imageData[i] / counts[i];

                color_table_get(message->palette, value, imageBuffer + i * 4);
            }
        }

        free(imageData);
        free(counts);

        if (save_image(message, &imData, imageBuffer)) {
            return 1;
        }

        free(imageBuffer);
    }
    logS.logName = settings->logName;

    free(data.data);

    return 0;
}

int generate_mrms_typed_refl(const MRMSTypedReflSettings* settings,
                             OutputImageAreas* output) {
    LogSettings logS = {
        .verbose = settings->verbose,
        .logName = settings->title,
    };

    DownloadSettings downloadS1 = {
        .verbose = settings->verbose,
        .logName = settings->title,
        .gzipped = settings->gzipped,
        .url     = settings->reflUrl,
        .timeout = settings->timeout,
    };
    DownloadedData data1 = download_data(&downloadS1);
    if (data1.error) {
        return 1;
    }
    MessageSettings message1 = {
        .palette     = NULL,
        .imageWidth  = settings->imageWidth,
        .imageHeight = settings->imageHeight,
        .title       = settings->title,
        .mode        = settings->mode,
        .offset      = 0,
        .minimum     = settings->minimum,
        .customArea  = settings->customArea,
        .area        = settings->area,
    };
    ImageData reflData = generate_image_data(&message1, data1.gribStart,
            data1.totalSize, settings->verbose, NULL, 0);
    free(data1.data);
    if (reflData.error) {
        return 1;
    }

    DownloadSettings downloadS2 = {
        .verbose = settings->verbose,
        .logName = settings->title,
        .gzipped = settings->gzipped,
        .url     = settings->typeUrl,
        .timeout = settings->timeout,
    };
    MessageSettings message2 = {
        .palette     = NULL,
        .imageWidth  = settings->imageWidth,
        .imageHeight = settings->imageHeight,
        .title       = settings->title,
        .mode        = Nearest_Data,
        .offset      = 0,
        .minimum     = -1,
        .customArea  = settings->customArea,
        .area        = settings->area,
    };
    DownloadedData data2 = download_data(&downloadS2);
    if (data2.error) {
        return 1;
    }
    ImageData typeData = generate_image_data(&message2, data2.gribStart,
            data2.totalSize, settings->verbose, NULL, 0);
    free(data2.data);
    if (typeData.error) {
        return 1;
    }

    if (fabs(reflData.coords.latT - typeData.coords.latT) > 0.00001 ||
        fabs(reflData.coords.latB - typeData.coords.latB) > 0.00001 ||
        fabs(reflData.coords.lonL - typeData.coords.lonL) > 0.00001 ||
        fabs(reflData.coords.lonR - typeData.coords.lonR) > 0.00001 ) {
        fprintf(stderr, "Reflectivity and precipitation type lat/lons did not match.\n");
        return 1;
    }

    _log(&logS, "Rendering Image");

    png_image image;
    memset(&image, 0, sizeof(image));
    image.version = PNG_IMAGE_VERSION;
    image.format = PNG_FORMAT_RGBA;
    image.width  = settings->imageWidth;
    image.height = settings->imageHeight;
    image.flags = 0;
    uint8_t* imageBuffer = NULL;
    imageBuffer = malloc(PNG_IMAGE_SIZE(image));
    if (imageBuffer == NULL) {
        return 1;
    }
    png_image_free(&image);

    for (size_t i = 0; i < settings->imageWidth * settings->imageHeight; i++) {
        if (reflData.counts[i] == 0 || typeData.counts[i] == 0) {
            imageBuffer[i * 4 + 0] = 0;
            imageBuffer[i * 4 + 1] = 0;
            imageBuffer[i * 4 + 2] = 0;
            imageBuffer[i * 4 + 3] = 0;
        } else {
            double value = reflData.imageData[i] / reflData.counts[i];
            double type  = typeData.imageData[i];

            if (type < 0.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 1.9) {
                color_table_get(settings->rainPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 2.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 3.9) {
                color_table_get(settings->snowPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 5.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 6.9) {
                color_table_get(settings->rainPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 7.9) {
                color_table_get(settings->hailPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 9.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 10.9) {
                color_table_get(settings->rainPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 90.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 91.9) {
                color_table_get(settings->rainPalette, value,
                                imageBuffer + i * 4);
            } else if (type < 95.9) {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            } else if (type < 96.9) {
                color_table_get(settings->rainPalette, value,
                                imageBuffer + i * 4);
            } else {
                imageBuffer[i * 4 + 0] = 0;
                imageBuffer[i * 4 + 1] = 0;
                imageBuffer[i * 4 + 2] = 0;
                imageBuffer[i * 4 + 3] = 0;
            }
        }
    }

    free(reflData.imageData);
    free(reflData.counts);
    free(typeData.imageData);
    free(typeData.counts);

    MessageSettings saveMessage = {
        .tiled                  = settings->tiled,
        .topLeftImageFile       = settings->topLeftImageFile,
        .topRightImageFile      = settings->topRightImageFile,
        .bottomLeftImageFile    = settings->bottomLeftImageFile,
        .bottomRightImageFile   = settings->bottomRightImageFile,
        .imageWidth             = settings->imageWidth,
        .imageHeight            = settings->imageHeight,
    };

    if (save_image(&saveMessage, &reflData, imageBuffer)) {
        return 1;
    }
    free(imageBuffer);

    memcpy(output, &(saveMessage.output), sizeof(*output));

    return 0;
}
