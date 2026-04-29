#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "yaml.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    yaml_parser_t parser;
    yaml_token_t token;
    int done = 0;

    /* Initialize the parser */
    if (!yaml_parser_initialize(&parser)) {
        return 0;
    }

    /* Set the input string from fuzz data */
    yaml_parser_set_input_string(&parser, data, size);

    /* Scan all tokens until done or error */
    while (!done) {
        /* Call the function under test */
        if (!yaml_parser_scan(&parser, &token)) {
            /* Parser error - clean up and exit */
            yaml_token_delete(&token);
            break;
        }

        /* Check if we've reached the end of the stream */
        if (token.type == YAML_STREAM_END_TOKEN) {
            done = 1;
        }

        /* Delete the token to free any allocated memory */
        yaml_token_delete(&token);
    }

    /* Clean up the parser */
    yaml_parser_delete(&parser);

    return 0;
}