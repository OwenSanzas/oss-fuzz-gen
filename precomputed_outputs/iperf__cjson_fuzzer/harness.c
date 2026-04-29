#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "/src/iperf/src/cjson.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Create a null-terminated string from the input data
    char *str = (char *)malloc(size + 1);
    if (!str) {
        return 0;
    }
    memcpy(str, data, size);
    str[size] = '\0';

    // Call the function under test
    cJSON *json = cJSON_Parse(str);

    // Clean up if parsing succeeded
    if (json != NULL) {
        cJSON_Delete(json);
    }

    free(str);
    return 0;
}