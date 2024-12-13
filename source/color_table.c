#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>

#include "color_table.h"

int color_entry_compare(const void* a, const void* b) {
    return ((const ColorEntry*)a)->value - ((const ColorEntry*)b)->value;
}

void color_table_print(const ColorTable* self) {
    for (size_t i = 0; i < self->count; i++) {
        ColorEntry* entry = self->entries + i;
        printf("%lf: #%hhx%hhx%hhx%hhx\n", entry->value, entry->red, entry->green, entry->blue, entry->alpha);
    }
}

void color_table_get(const ColorTable* self, double value, uint8_t* color) {
    value = value * self->scale + self->offset;

    if (self->count == 0 ||
        value < self->entries[0].value) {
        color[0] = 0;
        color[1] = 0;
        color[2] = 0;
        color[3] = 0;
        return;
    } else if (value >= self->entries[self->count - 1].value) {
        ColorEntry* entry = self->entries + (self->count - 1);
        if (entry->has2) {
            color[0] = entry->red2;
            color[1] = entry->green2;
            color[2] = entry->blue2;
            color[3] = entry->alpha2;
        } else {
            color[0] = entry->red;
            color[1] = entry->green;
            color[2] = entry->blue;
            color[3] = entry->alpha;
        }
        return;
    }

    for (size_t index = 1; index < self->count; index++) {
        if (self->entries[index].value > value) {
            ColorEntry* lower = self->entries + (index - 1);
            ColorEntry* upper = self->entries + index;

            double pos = (value - lower->value) / (upper->value - lower->value);

            if (lower->has2) {
                color[0] = pos * (lower->red2   - lower->red)   + lower->red;
                color[1] = pos * (lower->green2 - lower->green) + lower->green;
                color[2] = pos * (lower->blue2  - lower->blue)  + lower->blue;
                color[3] = pos * (lower->alpha2 - lower->alpha) + lower->alpha;
            } else {
                color[0] = pos * (upper->red   - lower->red)   + lower->red;
                color[1] = pos * (upper->green - lower->green) + lower->green;
                color[2] = pos * (upper->blue  - lower->blue)  + lower->blue;
                color[3] = pos * (upper->alpha - lower->alpha) + lower->alpha;
            }

            return;
        }
    }

    fprintf(stderr, "Did not find color, should be unreachable.");
    color[0] = 0;
    color[1] = 0;
    color[2] = 0;
    color[3] = 0;
}

void color_table_free(ColorTable* self) {
    free(self->entries);
    free(self);
}

