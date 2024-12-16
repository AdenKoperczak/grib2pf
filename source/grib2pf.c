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
        while (data->out.size - data->out.current < size) {
            uint8_t* ptr = realloc(data->out.data, data->out.size + CHUNCK_SIZE);
            if (ptr == NULL) {
                fprintf(stderr, "Could not allocate buffer\n");
                return CURL_WRITEFUNC_ERROR;

            }
            data->out.data = ptr;
            data->out.size += CHUNCK_SIZE;
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
    OutputCoords coords;
    double* imageData;
    uint32_t* counts;
    int error;
} ImageData;

ImageData generate_image_data(MessageSettings* message, uint8_t* d, size_t size,
                            bool verbose) {
    ImageData output;
    output.error = 0;

    LogSettings logS = {
        .verbose = verbose,
        .logName = message->title,
    };
    codes_handle* h = codes_handle_new_from_message(NULL, d + message->offset,
            size - message->offset);
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
    }
    free(latLonValues);

    return output;
}

int generate_image(const Settings* settings, OutputCoords* output) {
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

    for (size_t messageIndex = 0; messageIndex < settings->messageCount;
            messageIndex++) {
        MessageSettings* message = settings->messages + messageIndex;
        ImageData imData = generate_image_data(message, data.gribStart,
                data.totalSize, settings->verbose);

        if (imData.error) {
            continue;
        }
        double*   imageData = imData.imageData;
        uint32_t* counts    = imData.counts;
        output->latT = imData.coords.latT;
        output->latB = imData.coords.latB;
        output->lonL = imData.coords.lonL;
        output->lonR = imData.coords.lonR;

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

        _log(&logS, "Rendering Image");

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

        if (png_image_write_to_file(&image,
                                    message->imageFile,
                                    0,
                                    imageBuffer,
                                    0,
                                    NULL) == 0) {
            fprintf(stderr, "Did not write image\n");
        }

        png_image_free(&image);
        free(imageBuffer);
    }

    free(data.data);

    return 0;
}

int generate_mrms_typed_refl(const MRMSTypedReflSettings* settings,
                             OutputCoords* output) {
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
        .imageFile   = "",
        .palette     = NULL,
        .imageWidth  = settings->imageWidth,
        .imageHeight = settings->imageHeight,
        .title       = settings->title,
        .mode        = settings->mode,
        .offset      = 0,
    };
    ImageData reflData = generate_image_data(&message1, data1.gribStart,
            data1.totalSize, settings->verbose);
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
        .imageFile   = "",
        .palette     = NULL,
        .imageWidth  = settings->imageWidth,
        .imageHeight = settings->imageHeight,
        .title       = settings->title,
        .mode        = Nearest_Fast_Data,
        .offset      = 0,
    };
    DownloadedData data2 = download_data(&downloadS2);
    if (data2.error) {
        return 1;
    }
    ImageData typeData = generate_image_data(&message2, data2.gribStart,
            data2.totalSize, settings->verbose);
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

    output->latT = reflData.coords.latT;
    output->latB = reflData.coords.latB;
    output->lonL = reflData.coords.lonL;
    output->lonR = reflData.coords.lonR;

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

    _log(&logS, "Rendering Image");

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

    if (png_image_write_to_file(&image,
                                settings->imageFile,
                                0,
                                imageBuffer,
                                0,
                                NULL) == 0) {
        fprintf(stderr, "Did not write image\n");
    }

    png_image_free(&image);
    free(imageBuffer);

    return 0;
}
