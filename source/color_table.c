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

#define STARTING_SIZE 8

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)

#define PARSE_COLOR_VALUE(TO_SET) {                     \
    long temp = strtol(current, &next, 10);             \
    if (current == next || temp < 0 || temp > 255) {    \
        free(new->entries);                             \
        free(new);                                      \
        fprintf(stderr, "Failed to parse a color " TOSTRING(TO_SET) " in color_table_read\n"); \
        return NULL;                                    \
    }                                                   \
    new->entries[count].TO_SET = temp;                  \
    current = next;                                     \
}

ColorTable* color_table_read(FILE* file) {
    char * line = NULL;
    size_t n    = 0;
    ssize_t length;

    ColorTable* new = malloc(sizeof(*new));
    if (new == NULL) {
        fprintf(stderr, "Failed to allocate in color_table_read\n");
        return NULL;
    }

    new->scale  = 1;
    new->offset = 0;

    new->entries = malloc(sizeof(ColorEntry) * STARTING_SIZE);
    new->count   = STARTING_SIZE;
    if (new->entries == NULL) {
        fprintf(stderr, "Failed to allocate in color_table_read\n");
        free(new);
        return NULL;
    }

    char * current;
    char * next;

    size_t count = 0;

    while ((length = getline(&line, &n, file)) >= 0) {
        for (size_t i = 0; i < length; i++) {
            if (line[i] == ';') {
                line[i] = '\0';
                length = i;
                break;
            }
        }

        if (length > 5 && memcmp(line, "Color:", 6) == 0) {
            current = line + 6;
            next = NULL;

            new->entries[count].value = strtod(current, &next);
            if (current == next) {
                free(new->entries);
                free(new);
                fprintf(stderr, "Failed to parse a value in color_table_read\n");
                return NULL;
            }
            current = next;

            PARSE_COLOR_VALUE(red);
            PARSE_COLOR_VALUE(green);
            PARSE_COLOR_VALUE(blue);
            new->entries[count].alpha = 255;

            new->entries[count].has2 = false;

            while (true) {
                if (current[0] == '\0') {
                    break;
                } else if (isdigit(current[0])) {
                    new->entries[count].has2 = true;
                    PARSE_COLOR_VALUE(red2);
                    PARSE_COLOR_VALUE(green2);
                    PARSE_COLOR_VALUE(blue2);
                    new->entries[count].alpha2 = 255;
                    break;
                } else if (isspace(current[0])) {
                    current++;
                }
            }

            count++;

        } else if (length > 6 && memcmp(line, "Color4:", 7) == 0) {
            current = line + 7;
            next = NULL;

            new->entries[count].value = strtod(current, &next);
            if (current == next) {
                free(new->entries);
                free(new);
                fprintf(stderr, "Failed to parse a value in color_table_read\n");
                return NULL;
            }
            current = next;

            PARSE_COLOR_VALUE(red);
            PARSE_COLOR_VALUE(green);
            PARSE_COLOR_VALUE(blue);
            PARSE_COLOR_VALUE(alpha);

            new->entries[count].has2 = false;

            while (true) {
                if (current[0] == '\0') {
                    break;
                } else if (isdigit(current[0])) {
                    new->entries[count].has2 = true;
                    PARSE_COLOR_VALUE(red2);
                    PARSE_COLOR_VALUE(green2);
                    PARSE_COLOR_VALUE(blue2);
                    PARSE_COLOR_VALUE(alpha2);
                    break;
                } else if (isspace(current[0])) {
                    current++;
                }
            }

            count++;
        }

        if (count == new->count) {
            new->count *= 2;
            ColorEntry* temp = realloc(new->entries,
                                       new->count * sizeof(ColorEntry));
            if (temp == NULL) {
                free(new->entries);
                free(new);
                fprintf(stderr, "Failed to allocate in color_table_read\n");
                return NULL;
            }
            new->entries = temp;
        }
    }
    free(line);

    // TODO read errno for getline

    qsort(new->entries, count, sizeof(ColorEntry), color_entry_compare);

    new->count = count; // TODO realloc

    return new;
}
#undef PARSE_COLOR_VALUE

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

