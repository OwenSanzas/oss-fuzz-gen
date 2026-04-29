Looking at the `plist_from_xml` function, it typically has the signature `plist_err_t plist_from_xml(const char *plist_xml, uint32_t length, plist_t *plist)`.

<solution>

#include <fuzzer/FuzzedDataProvider.h>
#include <plist/plist.h>

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  FuzzedDataProvider provider(data, size);

  // Consume the remaining bytes as a string to use as XML input
  std::string xml_data = provider.ConsumeRemainingBytesAsString();

  plist_t root_node = NULL;
  plist_from_xml(xml_data.c_str(), static_cast<uint32_t>(xml_data.size()), &root_node);

  if (root_node != NULL) {
    plist_free(root_node);
  }

  return 0;
}