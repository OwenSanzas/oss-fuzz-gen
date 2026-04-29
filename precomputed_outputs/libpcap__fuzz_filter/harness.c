#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <pcap/pcap.h>

int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    pcap_t *pcap_handle;
    struct bpf_program bpf;
    char errbuf[PCAP_ERRBUF_SIZE];
    char *filter;
    size_t filter_len;
    int optimize;
    bpf_u_int32 netmask;
    int ret;

    if (Size < 2) {
        return 0;
    }

    /* Use first byte to determine optimize flag and other options */
    optimize = (Data[0] & 0x01) ? 1 : 0;
    netmask = PCAP_NETMASK_UNKNOWN;

    /* Use second byte to determine filter string length */
    filter_len = Data[1];
    if (filter_len == 0) {
        filter_len = 1;
    }

    /* Make sure we have enough data for the filter string */
    if (Size < 2 + filter_len) {
        filter_len = Size - 2;
    }

    if (filter_len == 0) {
        return 0;
    }

    /* Create a null-terminated filter string from the fuzz data */
    filter = (char *)malloc(filter_len + 1);
    if (filter == NULL) {
        return 0;
    }
    memcpy(filter, Data + 2, filter_len);
    filter[filter_len] = '\0';

    /* Create a dead pcap handle for compilation purposes */
    /* Try different link types based on fuzz data */
    int link_types[] = {
        DLT_EN10MB,
        DLT_RAW,
        DLT_NULL,
        DLT_LOOP,
        DLT_IEEE802,
        DLT_SLIP,
        DLT_PPP,
        DLT_FDDI,
        DLT_ATM_RFC1483,
        DLT_IEEE802_11,
    };
    int num_link_types = sizeof(link_types) / sizeof(link_types[0]);
    int link_type_idx = Data[0] % num_link_types;

    pcap_handle = pcap_open_dead(link_types[link_type_idx], 65535);
    if (pcap_handle == NULL) {
        /* Fallback to ethernet */
        pcap_handle = pcap_open_dead(DLT_EN10MB, 65535);
        if (pcap_handle == NULL) {
            free(filter);
            return 0;
        }
    }

    /* Call the function under test */
    ret = pcap_compile(pcap_handle, &bpf, filter, optimize, netmask);

    if (ret == 0) {
        /* Successfully compiled, free the program */
        pcap_freecode(&bpf);
    }

    /* Also try with a different netmask */
    if (Size >= 6) {
        bpf_u_int32 custom_netmask = 0;
        memcpy(&custom_netmask, Data + 2, sizeof(bpf_u_int32) < filter_len ? sizeof(bpf_u_int32) : filter_len);

        ret = pcap_compile(pcap_handle, &bpf, filter, optimize, custom_netmask);
        if (ret == 0) {
            pcap_freecode(&bpf);
        }
    }

    /* Try with optimize=0 */
    ret = pcap_compile(pcap_handle, &bpf, filter, 0, PCAP_NETMASK_UNKNOWN);
    if (ret == 0) {
        pcap_freecode(&bpf);
    }

    /* Try with optimize=1 */
    ret = pcap_compile(pcap_handle, &bpf, filter, 1, PCAP_NETMASK_UNKNOWN);
    if (ret == 0) {
        pcap_freecode(&bpf);
    }

    pcap_close(pcap_handle);
    free(filter);

    return 0;
}