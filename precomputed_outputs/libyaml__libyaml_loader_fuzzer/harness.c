#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "yaml.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    yaml_parser_t parser;
    yaml_document_t document;

    /* Initialize the parser */
    if (!yaml_parser_initialize(&parser)) {
        return 0;
    }

    /* Set the input string */
    yaml_parser_set_input_string(&parser, data, size);

    /* Try to load documents until there are no more or an error occurs */
    while (1) {
        int result = yaml_parser_load(&parser, &document);
        if (!result) {
            /* Error occurred, stop parsing */
            yaml_document_delete(&document);
            break;
        }

        /* Check if the document is empty (end of stream) */
        if (!yaml_document_get_root_node(&document)) {
            yaml_document_delete(&document);
            break;
        }

        /* Delete the document and continue to next */
        yaml_document_delete(&document);
    }

    /* Clean up the parser */
    yaml_parser_delete(&parser);

    return 0;
}