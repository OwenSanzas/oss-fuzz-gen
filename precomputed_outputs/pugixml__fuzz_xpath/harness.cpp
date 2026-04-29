#include "../src/pugixml.hpp"
#include <fuzzer/FuzzedDataProvider.h>

#include <stdint.h>
#include <string.h>
#include <string>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  FuzzedDataProvider fdp(data, size);

  // Consume a portion of data for the XPath query string
  std::string xpath_str = fdp.ConsumeRandomLengthString(256);

  // Consume the rest for XML document
  std::string xml_str = fdp.ConsumeRemainingBytesAsString();

#ifndef PUGIXML_NO_EXCEPTIONS
  try
#endif
  {
    // Set up xpath variable set
    pugi::xpath_variable_set vars;

    // Create the xpath_query object with the query string and variable set
    pugi::xpath_query query(xpath_str.c_str(), &vars);

    // Parse an XML document from the remaining fuzz data
    pugi::xml_document doc;
    doc.load_buffer(xml_str.data(), xml_str.size(), pugi::parse_full);

    // Call evaluate_node_set on the document root
    pugi::xpath_node_set result = query.evaluate_node_set(doc);

    // Also try on individual nodes to exercise more code paths
    pugi::xml_node root = doc.document_element();
    if (root) {
      pugi::xpath_node_set result2 = query.evaluate_node_set(root);
      (void)result2;
    }

    // Use the result to prevent optimization
    (void)result;
  }
#ifndef PUGIXML_NO_EXCEPTIONS
  catch (const pugi::xpath_exception &) {
    // Expected for invalid XPath expressions
  }
  catch (const std::exception &) {
    // Catch any other standard exceptions
  }
#endif

  return 0;
}