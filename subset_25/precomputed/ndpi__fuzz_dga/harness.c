#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include "ndpi_api.h"
#include "ndpi_main.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct ndpi_detection_module_struct *ndpi_str = NULL;
    struct ndpi_flow_struct *flow = NULL;
    char *name = NULL;
    NDPI_PROTOCOL_BITMASK all;
    int result = 0;

    if (size == 0) {
        return 0;
    }

    /* Initialize ndpi detection module */
    ndpi_str = ndpi_init_detection_module(NULL);
    if (ndpi_str == NULL) {
        return 0;
    }

    /* Enable all protocols */
    NDPI_BITMASK_SET_ALL(all);
    ndpi_set_protocol_detection_bitmask2(ndpi_str, &all);

    /* Finalize initialization */
    ndpi_finalize_initialization(ndpi_str);

    /* Allocate flow structure */
    flow = (struct ndpi_flow_struct *)calloc(1, sizeof(struct ndpi_flow_struct));
    if (flow == NULL) {
        ndpi_exit_detection_module(ndpi_str);
        return 0;
    }

    /* Create a null-terminated string from the fuzzer input */
    name = (char *)malloc(size + 1);
    if (name == NULL) {
        free(flow);
        ndpi_exit_detection_module(ndpi_str);
        return 0;
    }

    memcpy(name, data, size);
    name[size] = '\0';

    /* Call the function under test with is_hostname = 1 */
    result = ndpi_check_dga_name(ndpi_str, flow, name, 1);

    /* Also try with is_hostname = 0 */
    result = ndpi_check_dga_name(ndpi_str, flow, name, 0);

    /* Try with NULL flow as well */
    result = ndpi_check_dga_name(ndpi_str, NULL, name, 1);

    /* Cleanup */
    free(name);
    free(flow);
    ndpi_exit_detection_module(ndpi_str);

    return 0;
}