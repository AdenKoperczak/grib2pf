#ifndef COLOR_TABLE_H
#define COLOR_TABLE_H

#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>

#if defined(_MSC_VER)
#include <BaseTsd.h>
typedef SSIZE_T ssize_t;
#endif


typedef struct {
    double value;
    uint8_t red, green, blue, alpha;
    bool has2;
    uint8_t red2, green2, blue2, alpha2;
} ColorEntry;

typedef struct {
    ColorEntry* entries;
    size_t count;

    double scale;
    double offset;
} ColorTable;

void color_table_print(const ColorTable* self);
ColorTable* color_table_read(FILE* file);
void color_table_get(const ColorTable* self, double value, uint8_t* color);
ssize_t color_table_get_index(const ColorTable* self, double value);
void color_table_free(ColorTable* self);

#endif
