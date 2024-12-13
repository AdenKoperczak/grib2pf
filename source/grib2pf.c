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

#ifdef _WIN32
#include <sys\timeb.h>
void _log(const Settings* settings, char* message) {
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

    printf("[%s.%03d] [%s] %s\n", buffer, frac, settings->title, message);
}
#else
void _log(const Settings* settings, char* message) {
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

    printf("[%s.%03d] [%s] %s\n", buffer, frac, settings->title, message);
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

int generate_image(const Settings* settings, OutputCoords* output) {
    int err = 0;
    double xM, yM, yB;
    size_t i;
    double missingValue = 1.0e36;
    uint8_t* imageBuffer = NULL;

    double* imageData = NULL;
    uint32_t* counts   = NULL;

    double lonL, lonR, latT, latB;

    size_t totalSize;

    png_image image;

    codes_handle* h = NULL;
    codes_iterator* iter = NULL;

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

    _log(settings, "Downloading");
    err = inflateInit2(&(data.strm), 15 + 16);
    if (err != Z_OK) {
        fprintf(stderr, "Could not initialize zlib stream\n");
        return 1;
    }

    curl = curl_easy_init();
    if (curl == NULL) {
        fprintf(stderr, "Could not initialize curl\n");
        return 1;
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
        return 1;
    }
    curl_easy_cleanup(curl);
    if (settings->gzipped) {
        totalSize = data.strm.total_out;
    } else {
        totalSize = data.out.current;
    }
    inflateEnd(&(data.strm));

    _log(settings, "Preparing Data");

    uint8_t* d = data.out.data;
    i = 4;
    while (i < totalSize) {
        if (memcmp(d, "GRIB", 4) == 0) {
            break;
        }
        d++;
        i++;
    }
    totalSize = totalSize + 4 - i;

    h = codes_handle_new_from_message(NULL, d, totalSize);
    if (h == NULL) {
        fprintf(stderr, "Could not read in product\n");
        return 1;
    }

    size_t latLonValuesSize;
    double* latLonValues;
    CODES_CHECK(codes_get_size(h, "latLonValues", &latLonValuesSize), 0);
    latLonValues = malloc(latLonValuesSize * sizeof(double));
    if (latLonValues == NULL) {
        return 1;
    }
    CODES_CHECK(codes_get_double_array(h, "latLonValues",
                latLonValues, &latLonValuesSize), 0);

    if (settings->mode != Nearest_Data) {
        codes_handle_delete(h);
        free(data.out.data);
    }

    lonL = 1000;
    lonR = -1000;
    latB = 1000;
    latT = -1000;

    for (i = 0; i < latLonValuesSize; i += 3) {
        double lat = latLonValues[i + 0];
        double lon = latLonValues[i + 1];
        if (lon > lonR)
            lonR = lon;
        if (lon < lonL)
            lonL = lon;
        if (lat > latT)
            latT = lat;
        if (lat < latB)
            latB = lat;
    }

    output->lonL = lonL;
    output->lonR = lonR;
    output->latT = latT;
    output->latB = latB;

    xM = (settings->imageWidth - 0.01)  / (lonR - lonL);
    yM = (settings->imageHeight - 0.01) / (PROJECT_LAT_Y(latB) - PROJECT_LAT_Y(latT));
    yB = PROJECT_LAT_Y(latT);

    imageData = calloc(settings->imageWidth * settings->imageHeight, sizeof(*imageData));
    counts    = calloc(settings->imageWidth * settings->imageHeight, sizeof(*counts));
    if (imageData == NULL || counts == NULL) {
        return 1;
    }

    double lastLat = -10000;
    double lastY   = 0;

    switch (settings->mode) {
    case Average_Data:
        for (i = 0; i < latLonValuesSize; i += 3) {
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
                    x >= settings->imageWidth || y >= settings->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * settings->imageWidth;

            imageData[index] += value;
            counts[index]    += 1;
        }
        break;
    case Nearest_Data:
        double* nearestDist = malloc(settings->imageWidth * settings->imageHeight * sizeof(*nearestDist));
        if (nearestDist == NULL) {
            return 1;
        }
        for (i = 0; i < settings->imageWidth * settings->imageHeight; i++) {
            nearestDist[i] = 2; // distances should be < 1
        }
        for (i = 0; i < latLonValuesSize; i += 3) {
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
                    x >= settings->imageWidth || y >= settings->imageHeight) {
                continue;
            }
            size_t iX = (size_t) x;
            size_t iY = (size_t) y;
            size_t index = iX + iY * settings->imageWidth;

            double dx = (x - (iX + 0.5));
            double dy = (y - (iY + 0.5));
            double dist = sqrt(dx * dx + dy * dy);

            if (nearestDist[index] > dist) {
                imageData[index]   = value;
                counts[index]      = 1;
                nearestDist[index] = dist;
            }
        }
        break;
    }
    free(latLonValues);

    memset(&image, 0, sizeof(image));
    image.version = PNG_IMAGE_VERSION;
    image.format = PNG_FORMAT_RGBA;
    image.width  = settings->imageWidth;
    image.height = settings->imageHeight;
    image.flags = 0;

    imageBuffer = malloc(PNG_IMAGE_SIZE(image));
    if (imageBuffer == NULL) {
        return 1;
    }

    _log(settings, "Rendering Image");

    for (i = 0; i < settings->imageWidth * settings->imageHeight; i++) {
        if (counts[i] == 0) {
            imageBuffer[i * 4 + 0] = 0;
            imageBuffer[i * 4 + 1] = 0;
            imageBuffer[i * 4 + 2] = 0;
            imageBuffer[i * 4 + 3] = 0;
        } else {
            double value = imageData[i] / counts[i];

            color_table_get(settings->palette, value, imageBuffer + i * 4);
        }
    }

    free(imageData);
    free(counts);

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
