#include <fuzzer/FuzzedDataProvider.h>

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>

#include "deflate.h"
#include "zopfli.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  ZopfliOptions options;
  ZopfliInitOptions(&options);

  FuzzedDataProvider stream(data, size);

  // Limit iterations to avoid timeout
  options.numiterations = stream.ConsumeIntegralInRange<int>(1, 5);
  options.blocksplitting = stream.ConsumeBool() ? 1 : 0;
  options.blocksplittingmax = stream.ConsumeIntegralInRange<int>(1, 15);

  // From documentation: valid values for btype are 0, 1, or 2.
  const int btype = stream.PickValueInArray({0, 1, 2});
  // The final parameter is an int but it is used as a bool.
  const int is_final = stream.ConsumeIntegralInRange<int>(0, 1);

  const std::string input = stream.ConsumeRemainingBytesAsString();

  unsigned char *out = nullptr;
  size_t outsize = 0;
  unsigned char bp = 0; // Must be zero initially.

  ZopfliDeflate(&options, btype, is_final,
                reinterpret_cast<const unsigned char *>(input.data()),
                input.size(), &bp, &out, &outsize);

  if (out != nullptr) {
    free(out);
  }

  return 0;
}