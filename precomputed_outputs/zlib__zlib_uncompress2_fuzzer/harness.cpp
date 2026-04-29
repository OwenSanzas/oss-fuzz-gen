#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>
#include <zlib.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size == 0) {
    return 0;
  }

  // Use the first byte to determine destination buffer size multiplier
  uint8_t multiplier = data[0];
  const uint8_t* source_data = data + 1;
  size_t source_size = size - 1;

  if (source_size == 0) {
    return 0;
  }

  // Choose a destination buffer size based on multiplier
  // Try various sizes to exercise different paths
  size_t dest_size = static_cast<size_t>(multiplier) * source_size + source_size + 1;
  
  // Cap at reasonable size to avoid OOM
  if (dest_size > 1024 * 1024) {
    dest_size = 1024 * 1024;
  }

  std::vector<uint8_t> dest_buffer(dest_size);

  uLong actual_source_len = static_cast<uLong>(source_size);
  uLongf dest_len = static_cast<uLongf>(dest_buffer.size());

  // Call the function under test
  uncompress2(
      reinterpret_cast<Bytef*>(dest_buffer.data()),
      &dest_len,
      reinterpret_cast<const Bytef*>(source_data),
      &actual_source_len
  );

  return 0;
}