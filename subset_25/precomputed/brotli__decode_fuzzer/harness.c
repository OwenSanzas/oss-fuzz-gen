#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#include <brotli/decode.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  size_t addend = 0;
  if (size > 0)
    addend = data[size - 1] & 7;
  const uint8_t *next_in = data;

  const int kBufferSize = 1024;
  uint8_t *buffer = (uint8_t *)malloc(kBufferSize);
  if (!buffer) {
    return 0;
  }

  const size_t total_out_limit = (addend == 0) ? (1 << 26) : (1 << 24);
  size_t total_out = 0;

  BrotliDecoderState *state = BrotliDecoderCreateInstance(NULL, NULL, NULL);
  if (!state) {
    free(buffer);
    return 0;
  }

  if (addend == 0)
    addend = size > 0 ? size : 1;

  for (size_t i = 0; i < size;) {
    size_t next_i = i + addend;
    if (next_i > size)
      next_i = size;
    size_t avail_in = next_i - i;
    i = next_i;

    BrotliDecoderResult result = BROTLI_DECODER_RESULT_NEEDS_MORE_OUTPUT;
    while (result == BROTLI_DECODER_RESULT_NEEDS_MORE_OUTPUT) {
      size_t avail_out = kBufferSize;
      uint8_t *next_out = buffer;
      result = BrotliDecoderDecompressStream(
          state, &avail_in, &next_in, &avail_out, &next_out, &total_out);
      if (total_out > total_out_limit)
        break;
    }

    if (total_out > total_out_limit)
      break;
    if (result != BROTLI_DECODER_RESULT_NEEDS_MORE_INPUT)
      break;
  }

  BrotliDecoderDestroyInstance(state);
  free(buffer);
  return 0;
}