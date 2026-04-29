#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <libxslt/xslt.h>
#include <libxslt/xsltutils.h>

/* Include the fuzz header which declares xsltFuzzXPath */
#include "fuzz.h"

int LLVMFuzzerInitialize(int *argc, char ***argv) {
    (void)argc;
    (void)argv;
    /* Initialize the XPath fuzzing context */
    xsltFuzzXPathInit();
    return 0;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    xmlXPathObjectPtr xpathObj = NULL;

    if (size == 0) {
        return 0;
    }

    /* Call the function under test */
    xpathObj = xsltFuzzXPath((const char *)data, size);

    /* Free the result if non-NULL */
    if (xpathObj != NULL) {
        xsltFuzzXPathFreeObject(xpathObj);
    }

    return 0;
}