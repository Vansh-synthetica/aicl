// aicl_shm.cpp - C++ wrapper implementation for AICL Shared Memory Transport
#include <aicl/aicl_shm.hpp>
#include <cstring>

namespace aicl {

std::unique_ptr<ShmTransport> ShmTransport::createProducer(const ShmConfig& config) {
    auto t = std::make_unique<ShmTransport>();
    aicl_shm_config_t cfg = {};
    cfg.name = config.name.c_str();
    cfg.slot_size = config.slot_size;
    cfg.slot_count = config.slot_count;

    aicl_shm_t* handle = nullptr;
    if (aicl_shm_create_producer(&cfg, &handle) != AICL_SHM_OK) {
        t->error_ = "failed to create producer";
        return nullptr;
    }
    t->handle_ = handle;
    return t;
}

std::unique_ptr<ShmTransport> ShmTransport::openConsumer(const std::string& name) {
    auto t = std::make_unique<ShmTransport>();
    aicl_shm_t* handle = nullptr;
    if (aicl_shm_open_consumer(name.c_str(), &handle) != AICL_SHM_OK) {
        t->error_ = "failed to open consumer";
        return nullptr;
    }
    t->handle_ = handle;
    return t;
}

ShmTransport::~ShmTransport() {
    if (handle_) aicl_shm_destroy(handle_);
}

bool ShmTransport::send(const void* data, usize len, usize* out_sent) {
    if (!handle_) return false;
    usize sent = 0;
    auto status = aicl_shm_send(handle_, (const u8*)data, len, &sent);
    if (out_sent) *out_sent = sent;
    if (status != AICL_SHM_OK) {
        const char* err = aicl_shm_last_error(handle_);
        if (err) error_ = err;
        return false;
    }
    return true;
}

bool ShmTransport::recv(std::vector<u8>& out, usize* out_len) {
    if (!handle_) return false;
    usize capacity = out.capacity();
    if (capacity < 65536) {
        out.reserve(65536);
        capacity = 65536;
    }
    usize received = 0;
    auto status = aicl_shm_recv(handle_, out.data(), capacity, &received);
    if (out_len) *out_len = received;
    if (status != AICL_SHM_OK) {
        const char* err = aicl_shm_last_error(handle_);
        if (err) error_ = err;
        return false;
    }
    out.resize(received);
    return true;
}

bool ShmTransport::registerBuffer(const void* data, usize len, ShmBufferRef& out_ref) {
    if (!handle_) return false;
    aicl_bufref_t ref = {};
    auto status = aicl_shm_register_buffer(handle_, (const u8*)data, len, &ref);
    if (status != AICL_SHM_OK) {
        const char* err = aicl_shm_last_error(handle_);
        if (err) error_ = err;
        return false;
    }
    out_ref.id = ref.id;
    out_ref.offset = ref.offset;
    out_ref.length = ref.length;
    out_ref.alignment = ref.alignment;
    out_ref.type = ref.type;
    out_ref.ownership = ref.ownership;
    out_ref.lifetime = ref.lifetime;
    return true;
}

bool ShmTransport::getBuffer(const ShmBufferRef& ref, const u8** out_data, usize* out_len) {
    if (!handle_) return false;
    aicl_bufref_t bufref = {};
    bufref.id = ref.id;
    bufref.offset = ref.offset;
    bufref.length = ref.length;
    bufref.alignment = ref.alignment;
    bufref.type = ref.type;
    bufref.ownership = ref.ownership;
    bufref.lifetime = ref.lifetime;
    return aicl_shm_get_buffer(handle_, &bufref, out_data, out_len) == AICL_SHM_OK;
}

bool ShmTransport::releaseBuffer(u64 buffer_id) {
    if (!handle_) return false;
    return aicl_shm_release_buffer(handle_, buffer_id) == AICL_SHM_OK;
}

bool ShmTransport::waitRead(u32 timeout_ms) {
    if (!handle_) return false;
    return aicl_shm_wait_read(handle_, timeout_ms) == AICL_SHM_OK;
}

bool ShmTransport::waitWrite(u32 timeout_ms) {
    if (!handle_) return false;
    return aicl_shm_wait_write(handle_, timeout_ms) == AICL_SHM_OK;
}

bool ShmTransport::isOpen() const {
    return handle_ && aicl_shm_is_open(handle_);
}

std::string ShmTransport::lastError() const {
    if (!handle_) return error_;
    const char* err = aicl_shm_last_error(handle_);
    return err ? err : error_;
}

} // namespace aicl
