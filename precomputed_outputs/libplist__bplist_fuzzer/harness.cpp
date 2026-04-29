#include <fuzzer/FuzzedDataProvider.h>
#include <plist/plist.h>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  FuzzedDataProvider stream(data, size);

  // Consume remaining bytes as the binary plist data
  std::string plist_data = stream.ConsumeRemainingBytesAsString();

  plist_t root_node = NULL;
  plist_from_bin(plist_data.c_str(), (uint32_t)plist_data.size(), &root_node);

  if (root_node != NULL) {
    plist_free(root_node);
  }

  return 0;
}