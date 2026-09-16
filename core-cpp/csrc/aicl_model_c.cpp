// =============================================================================
//  aicl_model_c.c — C ABI shim for AICL Model Adapter
//  -----------------------------------------------------------------------------
//  C-compatible FFI layer consumed by Rust core-rust. All types are
//  C-layout-compatible and memory is managed via malloc/free for Rust FFI.
//
//  Design:
//   - No C++ exceptions cross the boundary (caught and mapped to status).
//   - Strings returned to Rust are malloc-allocated; caller frees via
//     aicl_free_string() or aicl_free_string_array().
//   - Buffer data is NEVER copied; only the 16-byte aicl_bufref_t descriptor.
//   - The underlying C++ adapter is thread-safe internally.
// =============================================================================

#include <aicl_model.h>
#include <aicl/aicl_adapter.hpp>
#include <aicl/aicl_value.hpp>
#include <aicl/aicl_model.hpp>

#include <stdlib.h>
#include <string.h>

// ---- Adapter instance (opaque) ---------------------------------------------
struct aicl_adapter {
    aicl::AICLModelAdapter* cpp;
    char* last_error;
};

static void aicl_set_error(aicl_adapter_t* self, const char* msg) {
    if (!self) return;
    free(self->last_error);
    size_t len = strlen(msg) + 1;
    self->last_error = (char*)malloc(len);
    if (self->last_error) memcpy(self->last_error, msg, len);
}

static void aicl_clear_error(aicl_adapter_t* self) {
    if (!self) return;
    free(self->last_error);
    self->last_error = NULL;
}

aicl_status_t aicl_adapter_create(aicl_adapter_t** out) {
    if (!out) return AICL_E_BAD_ARG;
    *out = NULL;

    aicl_adapter_t* self = (aicl_adapter_t*)calloc(1, sizeof(aicl_adapter_t));
    if (!self) return AICL_E_NOMEM;

    try {
        self->cpp = new aicl::AICLModelAdapter();
        *out = self;
        return AICL_OK;
    } catch (const std::exception& e) {
        aicl_set_error(self, e.what());
        free(self);
        return AICL_E_INTERNAL;
    } catch (...) {
        aicl_set_error(self, "unknown error in adapter create");
        free(self);
        return AICL_E_INTERNAL;
    }
}

aicl_status_t aicl_adapter_destroy(aicl_adapter_t* self) {
    if (!self) return AICL_E_BAD_ARG;
    delete self->cpp;
    free(self->last_error);
    free(self);
    return AICL_OK;
}

aicl_status_t aicl_adapter_install_backend(aicl_adapter_t* self,
                                           int backend_kind,
                                           const char* model_path,
                                           int n_ctx) {
    if (!self || !self->cpp) return AICL_E_BAD_ARG;
    aicl_clear_error(self);

    try {
        aicl::BackendKind kind = static_cast<aicl::BackendKind>(backend_kind);
        std::string path = model_path ? std::string(model_path) : std::string();
        self->cpp->install_backend(kind, path, n_ctx);
        return AICL_OK;
    } catch (const std::exception& e) {
        aicl_set_error(self, e.what());
        return AICL_E_BACKEND;
    } catch (...) {
        return AICL_E_BACKEND;
    }
}

aicl_status_t aicl_adapter_register_model(aicl_adapter_t* self,
                                          const char* name,
                                          const char* family,
                                          uint16_t* out_capref) {
    if (!self || !self->cpp || !out_capref) return AICL_E_BAD_ARG;
    aicl_clear_error(self);
    *out_capref = 0;

    try {
        aicl::ModelInfo info;
        info.id = name ? std::string(name) : std::string("unnamed");
        info.family = family ? std::string(family) : std::string("unknown");
        info.capabilities = {"text.generate"};

        auto model = aicl::load_model(aicl::BackendKind::Dummy, "", info);
        if (!model) return AICL_E_NO_MODEL;

        *out_capref = self->cpp->register_model(std::move(model), info.id);
        return AICL_OK;
    } catch (const std::exception& e) {
        aicl_set_error(self, e.what());
        return AICL_E_INTERNAL;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}
static void aicl_to_model_request(const aicl_call_t* in, aicl::ModelRequest& req) {
    req.target = in->cap_ref;
    req.deadline_ms = in->deadline_ms;
    req.flags = aicl::AiclFlags(in->flags);

    if (in->correlation_id) {
        memcpy(req.correlation_id.data(), in->correlation_id, 16);
    }

    if (in->inputs && in->inputs_count > 0) {
        for (size_t i = 0; i < in->inputs_count; ++i) {
            const char* key = in->inputs[i].key;
            const char* value = in->inputs[i].value;
            if (key && value) {
                req.inputs[std::string(key)] = aicl::Value::from_json(std::string(value));
            }
        }
    }

    if (in->input_buffers && in->input_buffers_count > 0) {
        req.input_buffers.reserve(in->input_buffers_count);
        for (size_t i = 0; i < in->input_buffers_count; ++i) {
            const aicl_bufref_t& src = in->input_buffers[i];
            aicl::BufferRef br{src.id, src.offset, src.length};
            req.input_buffers.push_back(br);
        }
    }
}

aicl_status_t aicl_adapter_handle_call(aicl_adapter_t* self,
                                       const aicl_call_t* in,
                                       aicl_call_t* out) {
    if (!self || !self->cpp || !in || !out) return AICL_E_BAD_ARG;
    aicl_clear_error(self);

    try {
        aicl::ModelRequest req;
        aicl_to_model_request(in, req);

        aicl::ModelResponse resp;
        self->cpp->handle_call(req, resp);

        // Mirror inputs as outputs (echo semantics for simple calls)
        for (const auto& kv : req.inputs) {
            resp.outputs[kv.first] = kv.second;
        }

        if (resp.error_code != 0) {
            if (!resp.error_message.empty()) {
                aicl_set_error(self, resp.error_message.c_str());
            }
            return static_cast<aicl_status_t>(resp.error_code);
        }

        return AICL_OK;
    } catch (const std::exception& e) {
        aicl_set_error(self, e.what());
        return AICL_E_INTERNAL;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

aicl_status_t aicl_adapter_handle_stream(aicl_adapter_t* self,
                                        const aicl_call_t* in,
                                        aicl_stream_callback cb,
                                        void* user) {
    if (!self || !self->cpp || !in || !cb) return AICL_E_BAD_ARG;
    aicl_clear_error(self);

    try {
        aicl::ModelRequest req;
        aicl_to_model_request(in, req);

        auto wrapped = [cb, user](const aicl::ModelResponse& chunk) -> bool {
            aicl_call_t c_out = {};
            c_out.cap_ref = chunk.target;
            // Lifetime: chunk lives for the duration of this call.  c_out
            // holds a *pointer* to the correlation_id bytes. The C caller
            // must copy if they need to retain it.
            uint8_t id_copy[16];
            memcpy(id_copy, chunk.correlation_id.data(), 16);
            c_out.correlation_id = id_copy;
            c_out.flags = static_cast<uint16_t>(chunk.flags.bits());
            return cb(&c_out, user);
        };

        self->cpp->handle_stream(req, wrapped);
        return AICL_OK;
    } catch (const std::exception& e) {
        aicl_set_error(self, e.what());
        return AICL_E_INTERNAL;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

aicl_status_t aicl_adapter_cancel(aicl_adapter_t* self, const uint8_t* correlation_id) {
    if (!self || !self->cpp || !correlation_id) return AICL_E_BAD_ARG;
    aicl_clear_error(self);

    try {
        aicl::Uuid uuid;
        memcpy(uuid.data(), correlation_id, 16);
        self->cpp->handle_cancel(uuid);
        return AICL_OK;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

aicl_status_t aicl_adapter_capabilities(aicl_adapter_t* self,
                                        char*** out_names,
                                        size_t* out_count) {
    if (!self || !self->cpp || !out_names || !out_count) return AICL_E_BAD_ARG;
    aicl_clear_error(self);

    try {
        std::vector<std::string> caps = self->cpp->advertised_capabilities();
        *out_count = caps.size();

        if (caps.empty()) {
            *out_names = NULL;
            return AICL_OK;
        }

        char** arr = (char**)malloc(sizeof(char*) * caps.size());
        if (!arr) return AICL_E_NOMEM;

        for (size_t i = 0; i < caps.size(); ++i) {
            arr[i] = (char*)malloc(caps[i].size() + 1);
            if (arr[i]) {
                memcpy(arr[i], caps[i].c_str(), caps[i].size() + 1);
            }
        }

        *out_names = arr;
        return AICL_OK;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

const char* aicl_adapter_last_error(aicl_adapter_t* self) {
    if (!self) return "";
    return self->last_error ? self->last_error : "";
}

aicl_status_t aicl_adapter_buffer_register_copy(aicl_adapter_t* self,
                                                const uint8_t* data,
                                                size_t len,
                                                uint64_t* out_id) {
    if (!self || !self->cpp || !data || !out_id) return AICL_E_BAD_ARG;
    *out_id = 0;
    aicl_clear_error(self);

    try {
        auto buf = std::make_shared<std::vector<uint8_t>>(data, data + len);
        *out_id = self->cpp->context().buffers().register_buffer(buf);
        return AICL_OK;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

aicl_status_t aicl_adapter_buffer_get(aicl_adapter_t* self,
                                       uint64_t id,
                                       const uint8_t** out_data,
                                       size_t* out_len) {
    if (!self || !self->cpp || !out_data || !out_len) return AICL_E_BAD_ARG;
    *out_data = NULL;
    *out_len = 0;
    aicl_clear_error(self);

    try {
        auto buf = self->cpp->context().buffers().get(id);
        if (!buf) return AICL_E_NOT_FOUND;

        *out_data = buf->data();
        *out_len = buf->size();
        return AICL_OK;
    } catch (...) {
        return AICL_E_INTERNAL;
    }
}

void aicl_free_string(const char* s) {
    free((void*)s);
}

void aicl_free_string_array(char** arr, size_t count) {
    if (!arr) return;
    for (size_t i = 0; i < count; ++i) {
        free(arr[i]);
    }
    free(arr);
}
