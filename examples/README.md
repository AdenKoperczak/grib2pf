# Example Settings Files

## Paths
Paths in these examples may start with `{intern_}`. This should be replaced
with the path to the `intern_` folder on Windows, or the source directory on
Linux. Placefile and image paths can be anything you like. Palette paths should
point to a valid palette file. Another note is that sometimes Windows will
remove extensions (`.jsonc`, `.txt`, `.png`, etc) when displaying names.

## Where are your settings
Your settings should be at `{intern_}/settings.jsonc`. You can modify it to
be more like one of the examples, or do your own thing with it.
`{intern_}/settings.json` is also a valid path, but should be moved to the
former for proper highlighting in text editors. Note that `\` must be replaced
by `\\` or `/` in any path.

## Settings Format
The settings are formatted using a modified version of JSON called JSONC.
(JSON with comments). Anything after a `//` and anything between a `/*` and `*/`
are comments, and ignored. I will continue to explain some basics of the JSONC
format as I go.

### Basic Formatting
The default settings use a single object for all the settings. This can be seen
in `default.jsonc`. The object is surrounded by `{` and `}`. Within that object,
there are "key-value pair's", which look something like below.
```
    "{key}": {value},
```
Anything in quotes is a string. To use a `\` you must use `\\` in strings. The
value can be a string or a number. **The comma is should not be used on the last
key-value pair in an object**.

### As an Array
`two-placefiles.jsonc` shows how to generate multiple placefiles. It simply
requires using JSONC arrays. An array starts with `[` ends with `]` and
contains several objects, separated by commas.

## Examples
- `default.jsonc` is the default settings file (plus comments). It creates a
  placefile based on Reflectivity data, and the WTC's reflectivity palette.
- `palette.jsonc` is like the `default.jsonc` file, but uses a custom palette.
- `precipitation-flag.jsonc` generates a placefile which classifies different
  precipitation types. Acts as a good example for non reflectivity products.
- `two-placefiles.jsonc` combines `default.jsonc` and
  `precipitation-flag.jsonc` to generate both placefiles.
- `to-host.jsonc` modifies the `default.jsonc` so the generated placefile can
  be hosted on a webserver.
