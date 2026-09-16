// =============================================================================
//  aicl_buffer.hpp
//  -----------------------------------------------------------------------------
//  Zero-copy buffer arena for tensor and embedding data sharing.
//
//  All heavy payload lives here. Modules reference data only via 16-byte
//  `BufferRef` handles. No bytes are copied when a `BufferRef` crosses the
//  module boundary — only the handle (id + offset + length).
//
//  Thread-safety: all public methods are thread-safe via a std::shared_mutex
//  (read-write lock). Multiple concurrent readers, single writer.
// =============================================================================
#pragma once

#include <aicl/aicl_value.hpp>

#include <memory>
#include <shared_mutex>
#include <unordered_map>
#include <vector>

namespace aicl {

/**
 * @brief Shared buffer arena for zero-copy data sharing.
 *
 * A buffer is registered with a unique u64 id. Callers receive only the id
 * and later pass `BufferRef{id, offset, length}` to indicate which slice they
 * mean. The data is kept alive by `shared_ptr` as long as any `BufferRef`
 * still references it.
 *
 * Registration of an existing `shared_ptr<vector<u8>>` keeps ownership with the
 * caller; `register_copy` makes an internal copy so the caller can free their
 * buffer.
 */
class BufferRegistry {
public:
    /// @brief Register an already-allocated buffer, returning a unique id.
    ///        The registry does NOT take ownership; the caller's shared_ptr
    ///        keeps the buffer alive.
    u64 register_buffer(std::shared_ptr<BytesBuffer> buf) {
        if (!buf || buf->empty()) return 0;
        std::unique_lock<std::shared_mutex> lk(mutex_);
        u64 id = next_id_++;
        // Steal the caller's shared_ptr, storing it in the map.
        // The refcount stays shared.
        map_.emplace(id, std::move(buf));
        return id;
    }

    /// @brief Register a copy of the given data, returning a new id.
    ///        The registry takes ownership of the copy.
    u64 register_copy(std::vector<u8> buf) {
        return register_buffer(std::make_shared<BytesBuffer>(std::move(buf)));
    }

    /// @brief Return a shared_ptr to the owning buffer for the given id.
    ///        Returns nullptr if the id is not registered.
    std::shared_ptr<BytesBuffer> get(u64 id) const {
        std::shared_lock<std::shared_mutex> lk(mutex_);
        auto it = map_.find(id);
        if (it == map_.end()) return {};
        return it->second;
    }

    /// @brief Release a buffer by id. Returns true if found and released.
    bool release(u64 id) {
        std::unique_lock<std::shared_mutex> lk(mutex_);
        auto it = map_.find(id);
        if (it == map_.end()) return false;
        map_.erase(it);
        return true;
    }

    /// @brief Byte size of a registered buffer (0 if not found).
    std::size_t size(u64 id) const {
        std::shared_lock<std::shared_mutex> lk(mutex_);
        auto it = map_.find(id);
        if (it == map_.end()) return 0;
        return it->second->size();
    }

    /// @brief Return a raw pointer to [offset, offset+length) in the buffer.
    ///        Returns nullptr if the buffer does not exist or bounds exceed.
    const u8* data(u64 id, u32 offset, u32 length) const {
        std::shared_lock<std::shared_mutex> lk(mutex_);
        auto it = map_.find(id);
        if (it == map_.end()) return nullptr;
        const auto& buf = *it->second;
        if (offset + length > buf.size()) return nullptr;
        return buf.data() + offset;
    }

    /// @brief Remove all registered buffers.
    void clear() {
        std::unique_lock<std::shared_mutex> lk(mutex_);
        map_.clear();
    }

    /// @brief Number of registered buffers.
    std::size_t count() const {
        std::shared_lock<std::shared_mutex> lk(mutex_);
        return map_.size();
    }

private:
    mutable std::shared_mutex mutex_;
    std::unordered_map<u64, std::shared_ptr<BytesBuffer>> map_;
    u64 next_id_ = 1; // 0 is reserved as invalid
};

} // namespace aicl
