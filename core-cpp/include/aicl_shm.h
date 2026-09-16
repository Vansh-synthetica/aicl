// aicl_shm.h - C API for AICL Shared Memory Transport
// Native same-machine IPC via shared memory ring buffer.
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum aicl_shm_status {
    AICL_SHM_OK=0, AICL_SHM_E_CREATE=1, AICL_SHM_E_OPEN=2, AICL_SHM_E_MAP=3,
    AICL_SHM_E_INVALID=4, AICL_SHM_E_CORRUPTED=5, AICL_SHM_E_TOO_LARGE=6,
    AICL_SHM_E_BACKPRESSURE=7, AICL_SHM_E_EMPTY=8, AICL_SHM_E_TIMEOUT=9,
    AICL_SHM_E_CLOSED=10,
} aicl_shm_status_t;

typedef struct aicl_shm aicl_shm_t;

// Buffer reference (zero-copy descriptor for shared memory data)
typedef struct aicl_bufref {
    uint64_t id;
    uint32_t offset;
    uint32_t length;
    uint16_t alignment;
    uint16_t type;
    uint8_t  ownership;
    uint8_t  lifetime;
    uint8_t  reserved[2];
} aicl_bufref_t;

typedef struct aicl_shm_config {
    const char* name;
    uint32_t    slot_size;
    uint32_t    slot_count;
} aicl_shm_config_t;

// Lifecycle
aicl_shm_status_t aicl_shm_create_producer(const aicl_shm_config_t* config, aicl_shm_t** out);
aicl_shm_status_t aicl_shm_open_consumer(const char* name, aicl_shm_t** out);
aicl_shm_status_t aicl_shm_destroy(aicl_shm_t* self);

// Packet send/receive (small messages inline in ring buffer)
aicl_shm_status_t aicl_shm_send(aicl_shm_t* self, const uint8_t* data, size_t len, size_t* out_sent);
aicl_shm_status_t aicl_shm_recv(aicl_shm_t* self, uint8_t* out_buf, size_t buf_size, size_t* out_received);

// Buffer operations (large messages via BUF_REF)
aicl_shm_status_t aicl_shm_register_buffer(aicl_shm_t* self, const uint8_t* data, size_t len, aicl_bufref_t* out_ref);
aicl_shm_status_t aicl_shm_get_buffer(aicl_shm_t* self, const aicl_bufref_t* ref, const uint8_t** out_data, size_t* out_len);
aicl_shm_status_t aicl_shm_release_buffer(aicl_shm_t* self, uint64_t buffer_id);

// Synchronization
aicl_shm_status_t aicl_shm_wait_read(aicl_shm_t* self, uint32_t timeout_ms);
aicl_shm_status_t aicl_shm_wait_write(aicl_shm_t* self, uint32_t timeout_ms);

// Status
int aicl_shm_is_open(aicl_shm_t* self);
const char* aicl_shm_last_error(aicl_shm_t* self);
void aicl_shm_free_error(const char* err);

#ifdef __cplusplus
}
#endif
