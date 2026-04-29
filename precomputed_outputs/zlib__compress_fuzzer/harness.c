#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    /* Output buffer for compressed data */
    uLongf destLen;
    Bytef *dest = NULL;
    int ret;
    int level;
    uLong sourceLen;

    if (size == 0) {
        return 0;
    }

    sourceLen = (uLong)size;

    /* compressBound gives the maximum size of the compressed output */
    destLen = compressBound(sourceLen);

    dest = (Bytef *)malloc(destLen);
    if (dest == NULL) {
        return 0;
    }

    /* Try different compression levels */
    /* Level 0: no compression */
    ret = compress2(dest, &destLen, (const Bytef *)data, sourceLen, Z_NO_COMPRESSION);
    (void)ret;

    /* Reset destLen for next call */
    destLen = compressBound(sourceLen);

    /* Level 1: best speed */
    ret = compress2(dest, &destLen, (const Bytef *)data, sourceLen, Z_BEST_SPEED);
    (void)ret;

    /* Reset destLen for next call */
    destLen = compressBound(sourceLen);

    /* Level 6: default compression */
    ret = compress2(dest, &destLen, (const Bytef *)data, sourceLen, Z_DEFAULT_COMPRESSION);
    (void)ret;

    /* Reset destLen for next call */
    destLen = compressBound(sourceLen);

    /* Level 9: best compression */
    ret = compress2(dest, &destLen, (const Bytef *)data, sourceLen, Z_BEST_COMPRESSION);
    (void)ret;

    /* Try using first byte of data to determine compression level */
    if (size > 1) {
        int dynamic_level;
        uLongf destLen2;
        Bytef *dest2 = NULL;

        dynamic_level = (int)(data[0] % 10) - 1; /* -1 to 8 */

        destLen2 = compressBound(sourceLen - 1);
        dest2 = (Bytef *)malloc(destLen2);
        if (dest2 != NULL) {
            ret = compress2(dest2, &destLen2, (const Bytef *)(data + 1), sourceLen - 1, dynamic_level);
            (void)ret;
            free(dest2);
        }
    }

    /* Try with invalid level to test error handling */
    destLen = compressBound(sourceLen);
    ret = compress2(dest, &destLen, (const Bytef *)data, sourceLen, 10); /* invalid level */
    (void)ret;

    /* Try with very small destLen to trigger Z_BUF_ERROR */
    if (size > 4) {
        uLongf smallDestLen = 1;
        ret = compress2(dest, &smallDestLen, (const Bytef *)data, sourceLen, Z_DEFAULT_COMPRESSION);
        (void)ret;
    }

    free(dest);
    return 0;
}