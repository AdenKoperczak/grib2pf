#define _USE_MATH_DEFINES
#define GRIB2PF_LIBRARY
#include "grib2pf.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>

#include "png.h"
#include "eccodes.h"
#include "zlib.h"
#include "curl/curl.h"
#include "color_table.h"

#define PROJECT_LAT_Y(lat) log(tan(M_PI / 4 + M_PI * lat / 360))


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
    double lat, lon, value;
    double x, y, xM, yM, yB;
    size_t iX, iY, i;
    double missingValue = 1.0e36;
    long bitmapPresent = 0;
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

    iter = codes_grib_iterator_new(h, 0, &err);
    if (err != CODES_SUCCESS) CODES_CHECK(err, 0);

    lonL = 1000;
    lonR = -1000;
    latB = 1000;
    latT = -1000;

    while (codes_grib_iterator_next(iter, &lat, &lon, &value)) {
        if (lon > lonR)
            lonR = lon;
        if (lon < lonL)
            lonL = lon;
        if (lat > latT)
            latT = lat;
        if (lat < latB)
            latB = lat;
    }

    codes_grib_iterator_delete(iter);

    output->lonL = lonL;
    output->lonR = lonR;
    output->latT = latT;
    output->latB = latB;

    xM = (settings->imageWidth - 0.01)  / (lonR - lonL);
    yM = (settings->imageHeight - 0.01) / (PROJECT_LAT_Y(latB) - PROJECT_LAT_Y(latT));
    yB = PROJECT_LAT_Y(latT);

    CODES_CHECK(codes_get_long(h, "bitmapPresent", &bitmapPresent), 0);
    if (bitmapPresent) {
        CODES_CHECK(codes_set_double(h, "missingValue", missingValue), 0);
    }

    iter = codes_grib_iterator_new(h, 0, &err);
    if (err != CODES_SUCCESS) CODES_CHECK(err, 0);

    imageData = calloc(settings->imageWidth * settings->imageHeight, sizeof(*imageData));
    counts    = calloc(settings->imageWidth * settings->imageHeight, sizeof(*counts));
    if (imageData == NULL || counts == NULL) {
        return 1;
    }

    while (codes_grib_iterator_next(iter, &lat, &lon, &value)) {
        x = (lon - lonL) * xM;
        y = (PROJECT_LAT_Y(lat) - yB) * yM;

        if (x < 0 || y < 0) {
            fprintf(stderr, "Coordinate (%lf,%lf) out of range\n", x, y);
            continue;
        }
        iX = (size_t) x; // TODO round
        iY = (size_t) y;
        if (iX >= settings->imageWidth || iY >= settings->imageHeight) {
            fprintf(stderr, "Coordinate (%lf,%lf) out of range\n", x, y);
            continue;
        }
        i = iX + iY * settings->imageWidth;

        if (bitmapPresent && value == missingValue) {
            fprintf(stderr, "Missing Value\n");
            continue;
        }

        imageData[i] += value;
        counts[i]    += 1;
    }

    codes_grib_iterator_delete(iter);
    codes_handle_delete(h);
    free(data.out.data);

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

    for (i = 0; i < settings->imageWidth * settings->imageHeight; i++) {
        if (counts[i] == 0) {
            imageBuffer[i * 4 + 0] = 0;
            imageBuffer[i * 4 + 1] = 0;
            imageBuffer[i * 4 + 2] = 0;
            imageBuffer[i * 4 + 3] = 0;
        } else {
            value = imageData[i] / counts[i];

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
