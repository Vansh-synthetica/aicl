// aicl_shm.hpp - C++ wrapper for AICL Shared Memory Transport
// Zero-copy shared memory IPC. No HTTP, localhost, or REST.
#pragma once

#include <aicl_shm.h>
#include <memory>
#include <string>
#include <vector>

namespace aicl {

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usize = std::size_t;

/// Buffer reference (zero-copy descriptor for shared memory data).
struct ShmBufferRef {
    u64 id = 0;
    u32 offset = 0;
    u32 length = 0;
    u16 alignment = 64;
    u16 type = 0;
    u8  ownership = 0;
    u8  lifetime = 0;

    static constexpr usize SIZE = 24;
    bool is_valid() const { return length > 0 && offset > 0; }
};

/// Configuration for shared memory transport.
struct ShmConfig {
    std::string name = "aicl-default";
    u32 slot_size = 4096;
    u32 slot_count = 256;
};

/// Shared memory transport for AICL.
class ShmTransport {
public:
    static std::unique_ptr<ShmTransport> createProducer(const ShmConfig& config);
    static std::unique_ptr<ShmTransport> openConsumer(const std::string& name);

    ~ShmTransport();
    ShmTransport(const ShmTransport&) = delete;
    ShmTransport& operator=(const ShmTransport&) = delete;

    // Small message: inline in ring buffer
    bool send(const void* data, usize len, usize* out_sent = nullptr);
    bool recv(std::vector<u8>& out, usize* out_len = nullptr);

    // Large message: via BUF_REF
    bool registerBuffer(const void* data, usize len, ShmBufferRef& out_ref);
    bool getBuffer(const ShmBufferRef& ref, const u8** out_data, usize* out_len);
    bool releaseBuffer(u64 buffer_id);

    // Synchronization
    bool waitRead(u32 timeout_ms);
    bool waitWrite(u32 timeout_ms);

    // Status
    bool isOpen() const;
    std::string lastError() const;

private:
    ShmTransport() = default;
    aicl_shm_t* handle_ = nullptr;
    std::string error_;
};

} // namespace aicl
