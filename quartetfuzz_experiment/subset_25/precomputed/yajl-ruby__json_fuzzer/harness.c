#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "api/yajl_parse.h"

static int yajl_null(void *ctx) { return 1; }
static int yajl_boolean(void *ctx, int boolean) { return 1; }
static int yajl_integer(void *ctx, long long integerVal) { return 1; }
static int yajl_double(void *ctx, double doubleVal) { return 1; }
static int yajl_number(void *ctx, const char *numberVal, size_t numberLen) { return 1; }
static int yajl_string(void *ctx, const unsigned char *stringVal, size_t stringLen) { return 1; }
static int yajl_start_map(void *ctx) { return 1; }
static int yajl_map_key(void *ctx, const unsigned char *key, size_t stringLen) { return 1; }
static int yajl_end_map(void *ctx) { return 1; }
static int yajl_start_array(void *ctx) { return 1; }
static int yajl_end_array(void *ctx) { return 1; }

static yajl_callbacks callbacks = {
    yajl_null,
    yajl_boolean,
    NULL,
    NULL,
    yajl_number,
    yajl_string,
    yajl_start_map,
    yajl_map_key,
    yajl_end_map,
    yajl_start_array,
    yajl_end_array
};

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    yajl_parser_config cfg1 = { 1, 1 };
    yajl_parser_config cfg2 = { 0, 0 };
    yajl_parser_config cfg3 = { 1, 0 };
    yajl_parser_config cfg4 = { 0, 1 };

    yajl_handle handle;
    yajl_status status;

    /* Test with allowComments=1, checkUTF8=1 */
    handle = yajl_alloc(&callbacks, &cfg1, NULL, NULL);
    if (handle != NULL) {
        status = yajl_parse(handle, data, size);
        if (status == yajl_status_ok) {
            yajl_parse_complete(handle);
        }
        yajl_free(handle);
    }

    /* Test with allowComments=0, checkUTF8=0 */
    handle = yajl_alloc(&callbacks, &cfg2, NULL, NULL);
    if (handle != NULL) {
        status = yajl_parse(handle, data, size);
        if (status == yajl_status_ok) {
            yajl_parse_complete(handle);
        }
        yajl_free(handle);
    }

    /* Test with allowComments=1, checkUTF8=0 */
    handle = yajl_alloc(&callbacks, &cfg3, NULL, NULL);
    if (handle != NULL) {
        status = yajl_parse(handle, data, size);
        if (status == yajl_status_ok) {
            yajl_parse_complete(handle);
        }
        yajl_free(handle);
    }

    /* Test with allowComments=0, checkUTF8=1 */
    handle = yajl_alloc(&callbacks, &cfg4, NULL, NULL);
    if (handle != NULL) {
        status = yajl_parse(handle, data, size);
        if (status == yajl_status_ok) {
            yajl_parse_complete(handle);
        }
        yajl_free(handle);
    }

    /* Test with NULL callbacks */
    handle = yajl_alloc(NULL, &cfg1, NULL, NULL);
    if (handle != NULL) {
        status = yajl_parse(handle, data, size);
        if (status == yajl_status_ok) {
            yajl_parse_complete(handle);
        }
        yajl_free(handle);
    }

    /* Test incremental parsing - split data into two chunks */
    if (size > 1) {
        size_t split = size / 2;
        handle = yajl_alloc(&callbacks, &cfg1, NULL, NULL);
        if (handle != NULL) {
            status = yajl_parse(handle, data, split);
            if (status == yajl_status_ok || status == yajl_status_insufficient_data) {
                yajl_parse(handle, data + split, size - split);
                yajl_parse_complete(handle);
            }
            yajl_free(handle);
        }
    }

    return 0;
}