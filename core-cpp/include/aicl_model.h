// =============================================================================
//  aicl_model.h
//  -----------------------------------------------------------------------------
//  C ABI header for the AICL model adapter layer.
//  This header is consumed by the Rust side (core-rust) via bindgen or
//  manual FFI, so types use C-layout-compatible structs and malloc/free
//  for dynamic memory.
//
//  All functions return aicl_status_t (see enum below).
//
//  Memory ownership:
//   - All strings returned to the caller are allocated with malloc (for
//     compatibility with Rust's GlobalAlloc). The caller must call
//     aicl_free_string() or aicl_free_string_array() to release them.
//   - All aicl_call_t input structs are owned by the caller; the adapter
//     copies their contents.
//   - Buffer data is never copied; only the 16-byte BufferRef descriptor
//     (aicl_bufref_t) is copied.
// =============================================================================
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---- Status codes -----------------------------------------------------------
typedef enum aicl_status {
    AICL_OK          = 0,
    AICL_E_BAD_ARG   = 1,
    AICL_E_NO_MODEL  = 2,
    AICL_E_BACKEND   = 3,
    AICL_E_NOT_FOUND = 4,
    AICL_E_NOMEM     = 5,
    AICL_E_INTERNAL  = 6,
    AICL_E_CANCELLED = 7,
} aicl_status_t;

// ---- Buffer reference (16 bytes, matches C++ BufferRef) ----------------------
typedef struct aicl_bufref {
    uint64_t id;
    uint32_t offset;
    uint32_t length;
} aicl_bufref_t;

// ---- Capability frame (matches C++ ModelRequest / ModelResponse) -------------
// Input/output key-value pairs for a call.
typedef struct aicl_kv {
    const char* key;
    const char* value;   // JSON-encoded Value
} aicl_kv_t;

// Input/output buffers (zero-copy descriptors).
typedef struct aicl_call {
    uint16_t    cap_ref;           // Target model capability reference.
    uint8_t     correlation_id[16]; // 128-bit correlation UUID.
    uint32_t    deadline_ms;       // Wall-clock deadline (0 = none).
    uint16_t    flags;             // AiclFlags bits.

    // Key-value inputs (e.g. "prompt" -> JSON string, "temperature" -> "0.7").
    aicl_kv_t*  inputs;
    size_t      inputs_count;

    // Zero-copy buffer payloads.
    aicl_bufref_t* input_buffers;
    size_t          input_buffers_count;
} aicl_call_t;

// ---- Adapter lifetime -------------------------------------------------------
typedef struct aicl_adapter aicl_adapter_t;

// Create / destroy an adapter instance.
aicl_status_t aicl_adapter_create(aicl_adapter_t** out);
aicl_status_t aicl_adapter_destroy(aicl_adapter_t* self);

// ---- Backend / model registration -----------------------------------------
// backend_kind: 0 = Dummy, 1 = LlamaCpp (if compiled with AICL_WITH_LLAMA).
aicl_status_t aicl_adapter_install_backend(aicl_adapter_t* self,
                                          int backend_kind,
                                          const char* model_path,
                                          int n_ctx);

aicl_status_t aicl_adapter_register_model(aicl_adapter_t* self,
                                         const char* name,
                                         const char* family,
                                         uint16_t* out_capref);

// ---- Call dispatch ---------------------------------------------------------
// Single-shot non-streaming call.
aicl_status_t aicl_adapter_handle_call(aicl_adapter_t* self,
                                       const aicl_call_t* in,
                                       aicl_call_t* out);

// Streaming call: visitor is invoked per token chunk.
// typedef bool (*aicl_stream_callback)(const aicl_call_t* chunk, void* user);
typedef bool (*aicl_stream_callback)(const aicl_call_t* chunk, void* user);

aicl_status_t aicl_adapter_handle_stream(aicl_adapter_t* self,
                                        const aicl_call_t* in,
                                        aicl_stream_callback cb,
                                        void* user);

aicl_status_t aicl_adapter_cancel(aicl_adapter_t* self,
                                 const uint8_t* correlation_id);

// ---- Introspection ----------------------------------------------------------
// Returns a malloc-allocated array of char* strings; caller calls
// aicl_free_string_array() to release.
aicl_status_t aicl_adapter_capabilities(aicl_adapter_t* self,
                                        char*** out_names,
                                        size_t*  out_count);

// Returns a malloc-allocated string describing the last error.
const char* aicl_adapter_last_error(aicl_adapter_t* self);

// ---- Buffer registry (zero-copy) --------------------------------------------
// Register a copy of data; returns a buffer id that can be used in aicl_bufref_t.
aicl_status_t aicl_adapter_buffer_register_copy(aicl_adapter_t* self,
                                                const uint8_t* data,
                                                size_t         len,
                                                uint64_t*      out_id);

// Retrieve the raw pointer and length of a registered buffer.
// The pointer is valid until the buffer is released.
aicl_status_t aicl_adapter_buffer_get(aicl_adapter_t* self,
                                       uint64_t        id,
                                       const uint8_t** out_data,
                                       size_t*         out_len);

// ---- Memory helpers ---------------------------------------------------------
// Free a string returned by the C API.
void aicl_free_string(const char* s);

// Free a string array returned by the C API.
void aicl_free_string_array(char** arr, size_t count);

#ifdef __cplusplus
}
#endif
