#include <fuzzer/FuzzedDataProvider.h>
#include <plist/plist.h>
#include <cstddef>
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FuzzedDataProvider provider(data, size);
  
  // Consume the remaining bytes as a string for the plist input
  std::string input = provider.ConsumeRemainingBytesAsString();
  
  plist_t root_node = NULL;
  plist_from_openstep(input.c_str(), static_cast<uint32_t>(input.size()), &root_node);
  
  if (root_node != NULL) {
    plist_free(root_node);
  }
  
  return 0;
}