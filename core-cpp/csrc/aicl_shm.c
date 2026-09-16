// aicl_shm.c - C implementation of AICL Shared Memory Transport
// Native shared memory IPC for AICL. No HTTP, localhost, or REST.
#include <aicl_shm.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

// This is a stub implementation.
// Full implementation requires linking to the Rust aicl_core library.

struct aicl_shm {
    char* name;
    int is_producer;
    int is_open;
    char* last_error;
};

static void shm_set_error(aicl_shm_t* self, const char* msg) {
    if (!self) return;
    free(self->last_error);
    size_t len = strlen(msg) + 1;
    self->last_error = (char*)malloc(len);
    if (self->last_error) strcpy(self->last_error, msg);
}

static void shm_clear_error(aicl_shm_t* self) {
    if (!self) return;
    free(self->last_error);
    self->last_error = NULL;
}

aicl_shm_status_t aicl_shm_create_producer(const aicl_shm_config_t* config, aicl_shm_t** out) {
    if (!config || !out) return AICL_SHM_E_CREATE;
    *out = NULL;

    aicl_shm_t* self = (aicl_shm_t*)calloc(1, sizeof(aicl_shm_t));
    if (!self) return AICL_SHM_E_CREATE;

    self->name = (char*)malloc(config->name ? strlen(config->name) + 1 : 16);
    if (self->name) {
        if (config->name) strcpy(self->name, config->name);
        else strcpy(self->name, "aicl-default");
    }

    self->is_producer = 1;
    self->is_open = 1;
    *out = self;
    return AICL_SHM_OK;
}

aicl_shm_status_t aicl_shm_open_consumer(const char* name, aicl_shm_t** out) {
    if (!name || !out) return AICL_SHM_E_OPEN;
    *out = NULL;

    aicl_shm_t* self = (aicl_shm_t*)calloc(1, sizeof(aicl_shm_t));
    if (!self) return AICL_SHM_E_OPEN;

    self->name = (char*)malloc(strlen(name) + 1);
    if (self->name) strcpy(self->name, name);

    self->is_producer = 0;
    self->is_open = 1;
    *out = self;
    return AICL_SHM_OK;
}

aicl_shm_status_t aicl_shm_destroy(aicl_shm_t* self) {
    if (!self) return AICL_SHM_E_CLOSED;
    free(self->name);
    free(self->last_error);
    free(self);
    return AICL_SHM_OK;
}

aicl_shm_status_t aicl_shm_send(aicl_shm_t* self, const uint8_t* data, size_t len, size_t* out_sent) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    if (!self->is_producer) return AICL_SHM_E_INVALID;

    shm_set_error(self, "send not implemented - link to aicl_core library");
    return AICL_SHM_E_CLOSED; // Stub
}

aicl_shm_status_t aicl_shm_recv(aicl_shm_t* self, uint8_t* out_buf, size_t buf_size, size_t* out_received) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    if (self->is_producer) return AICL_SHM_E_INVALID;

    shm_set_error(self, "recv not implemented - link to aicl_core library");
    return AICL_SHM_E_CLOSED; // Stub
}

aicl_shm_status_t aicl_shm_register_buffer(aicl_shm_t* self, const uint8_t* data, size_t len, aicl_bufref_t* out_ref) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    shm_set_error(self, "register_buffer not implemented");
    return AICL_SHM_E_CLOSED; // Stub
}

aicl_shm_status_t aicl_shm_get_buffer(aicl_shm_t* self, const aicl_bufref_t* ref, const uint8_t** out_data, size_t* out_len) {
    if (!self || !self->is_open || !ref) return AICL_SHM_E_INVALID;
    return AICL_SHM_E_INVALID; // Stub
}

aicl_shm_status_t aicl_shm_release_buffer(aicl_shm_t* self, uint64_t buffer_id) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    return AICL_SHM_OK; // Stub
}

aicl_shm_status_t aicl_shm_wait_read(aicl_shm_t* self, uint32_t timeout_ms) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    return AICL_SHM_OK; // Stub
}

aicl_shm_status_t aicl_shm_wait_write(aicl_shm_t* self, uint32_t timeout_ms) {
    if (!self || !self->is_open) return AICL_SHM_E_CLOSED;
    return AICL_SHM_OK; // Stub
}

int aicl_shm_is_open(aicl_shm_t* self) {
    return self && self->is_open;
}

const char* aicl_shm_last_error(aicl_shm_t* self) {
    if (!self) return "";
    return self->last_error ? self->last_error : "";
}

void aicl_shm_free_error(const char* err) {
    // No-op for static strings
}

void aicl_shm_free_string(const char* s) {
    free((void*)s);
}
