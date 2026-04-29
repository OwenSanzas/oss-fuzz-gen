#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "jv.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    /* Create a null-terminated string from the fuzzer input */
    char *input = (char *)malloc(size + 1);
    if (input == NULL) {
        return 0;
    }
    memcpy(input, data, size);
    input[size] = '\0';

    /* Call the function under test */
    jv result = jv_parse(input);

    /* Check if the result is valid and free appropriately */
    if (jv_is_valid(result)) {
        /* Try some operations on the parsed value to exercise more code paths */
        jv_kind kind = jv_get_kind(result);

        if (kind == JV_KIND_ARRAY) {
            int len = jv_array_length(jv_copy(result));
            for (int i = 0; i < len && i < 10; i++) {
                jv elem = jv_array_get(jv_copy(result), i);
                jv_free(elem);
            }
        } else if (kind == JV_KIND_OBJECT) {
            int len = jv_object_length(jv_copy(result));
            (void)len;
        } else if (kind == JV_KIND_STRING) {
            int slen = jv_string_length_bytes(jv_copy(result));
            (void)slen;
        } else if (kind == JV_KIND_NUMBER) {
            double val = jv_number_value(result);
            (void)val;
        }

        /* Convert back to string */
        jv dumped = jv_dump_string(jv_copy(result), 0);
        if (jv_is_valid(dumped)) {
            const char *str = jv_string_value(dumped);
            (void)str;
        }
        jv_free(dumped);
    } else {
        /* Even invalid results need to be freed */
        jv error_msg = jv_invalid_get_msg(jv_copy(result));
        if (jv_is_valid(error_msg)) {
            const char *msg = jv_string_value(error_msg);
            (void)msg;
        }
        jv_free(error_msg);
    }

    jv_free(result);

    /* Also try parsing with explicit length using jv_parse_sized */
    jv result2 = jv_parse_sized(input, (int)size);
    if (jv_is_valid(result2)) {
        jv_kind kind2 = jv_get_kind(result2);
        (void)kind2;
    } else {
        jv error_msg2 = jv_invalid_get_msg(jv_copy(result2));
        jv_free(error_msg2);
    }
    jv_free(result2);

    free(input);
    return 0;
}