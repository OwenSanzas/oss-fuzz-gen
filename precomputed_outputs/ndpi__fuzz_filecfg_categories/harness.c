#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>

// Declare the function we're fuzzing
extern void load_categories_file_fd(int fd);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Create a temporary file to hold the fuzzer data
    char tmpfile_path[] = "/tmp/fuzz_categories_XXXXXX";
    int fd = -1;
    ssize_t written = 0;
    size_t total_written = 0;

    // Create a temporary file
    fd = mkstemp(tmpfile_path);
    if (fd < 0) {
        return 0;
    }

    // Write fuzzer data to the temp file
    while (total_written < size) {
        written = write(fd, data + total_written, size - total_written);
        if (written <= 0) {
            break;
        }
        total_written += (size_t)written;
    }

    // Seek back to the beginning of the file
    if (lseek(fd, 0, SEEK_SET) < 0) {
        close(fd);
        unlink(tmpfile_path);
        return 0;
    }

    // Call the function under test
    load_categories_file_fd(fd);

    // Cleanup
    close(fd);
    unlink(tmpfile_path);

    return 0;
}