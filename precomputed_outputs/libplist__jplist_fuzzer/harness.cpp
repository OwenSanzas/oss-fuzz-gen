#include <fuzzer/FuzzedDataProvider.h>
#include <plist/plist.h>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FuzzedDataProvider provider(data, size);

  // Consume the remaining bytes as a string to use as JSON input
  std::string json_input = provider.ConsumeRemainingBytesAsString();

  plist_t root_node = NULL;
  plist_from_json(json_input.c_str(), (uint32_t)json_input.size(), &root_node);

  if (root_node != NULL) {
    plist_free(root_node);
  }

  return 0;
}