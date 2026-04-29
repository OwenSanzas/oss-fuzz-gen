#include <stdint.h>
#include <stddef.h>
#include "fuzz.h"

int LLVMFuzzerInitialize(int *argc ATTRIBUTE_UNUSED, char ***argv ATTRIBUTE_UNUSED) {
    return xsltFuzzXsltInit();
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    xmlDocPtr result = xsltFuzzXslt((const char *)data, size);
    xmlFreeDoc(result);
    return 0;
}