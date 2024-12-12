#ifndef COLOR_TABLE_H
#define COLOR_TABLE_H

#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stddef.h>

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

ColorTable* color_table_read(FILE* file);
void color_table_get(const ColorTable* self, double value, uint8_t* color);
void color_table_free(ColorTable* self);

#endif
