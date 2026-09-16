// =============================================================================
//  aicl_context.hpp
//  -----------------------------------------------------------------------------
//  Per-process model context: owns the BufferRegistry and a registry of
//  loaded IModel instances, indexed by `CapRef`. The AICLModelAdapter
//  owns a single ModelContext and uses it to dispatch calls.
//
//  CapRef 0 is reserved (null cap) — never maps to a real model.
//
//  Thread-safety:
//   - register / unregister / lookup are guarded by a shared_mutex.
//   - Each model has its own internal mutex; concurrent dispatch to
//     different models is safe and parallel.
// =============================================================================
#pragma once

#include <aicl/aicl_buffer.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>

#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace aicl {

/**
 * @brief Owning context for all loaded models and shared buffers.
 *
 * A `ModelContext` outlives the adapter that owns it (typically process
 * lifetime). It exposes both a buffer arena and a model registry.
 */
class ModelContext {
public:
    ModelContext() = default;
    ~ModelContext() = default;

    ModelContext(const ModelContext&) = delete;
    ModelContext& operator=(const ModelContext&) = delete;

    /// @brief Register a model. Returns a non-zero CapRef on success.
    ///        CapRef 0 is reserved (null cap).
    u16 register_model(std::unique_ptr<IModel> m) {
        if (!m) return 0;
        std::unique_lock<std::shared_mutex> lk(reg_mutex_);
        // Find a free slot. CapRef is u16; 0 is reserved.
        u16 cap = next_cap_++;
        if (next_cap_ == 0) next_cap_ = 1; // skip the reserved 0
        models_.emplace(cap, std::move(m));
        return cap;
    }

    /// @brief Look up a model by CapRef. Returns nullptr if not found.
    IModel* lookup(u16 cap_ref) const {
        std::shared_lock<std::shared_mutex> lk(reg_mutex_);
        auto it = models_.find(cap_ref);
        if (it == models_.end()) return nullptr;
        return it->second.get();
    }

    /// @brief Look up a model by its `ModelInfo::id` (string match).
    IModel* lookup_by_name(const std::string& name) const {
        std::shared_lock<std::shared_mutex> lk(reg_mutex_);
        for (const auto& [cap, m] : models_) {
            if (m && m->info().id == name) return m.get();
        }
        return nullptr;
    }

    /// @brief Look up a model by CapRef, also returning the CapRef.
    IModel* lookup(u16 cap_ref, u16& out_cap) const {
        std::shared_lock<std::shared_mutex> lk(reg_mutex_);
        auto it = models_.find(cap_ref);
        if (it == models_.end()) return nullptr;
        out_cap = cap_ref;
        return it->second.get();
    }

    /// @brief Unregister a model. Returns true if it was present.
    bool unregister(u16 cap_ref) {
        std::unique_lock<std::shared_mutex> lk(reg_mutex_);
        auto it = models_.find(cap_ref);
        if (it == models_.end()) return false;
        models_.erase(it);
        return true;
    }

    /// @brief Number of registered models.
    std::size_t model_count() const {
        std::shared_lock<std::shared_mutex> lk(reg_mutex_);
        return models_.size();
    }

    /// @brief List all currently registered CapRefs.
    std::vector<u16> registered_caps() const {
        std::shared_lock<std::shared_mutex> lk(reg_mutex_);
        std::vector<u16> out;
        out.reserve(models_.size());
        for (const auto& [cap, _] : models_) out.push_back(cap);
        return out;
    }

    /// @brief Access the shared BufferRegistry.
    BufferRegistry&       buffers()       { return buffers_; }
    const BufferRegistry& buffers() const { return buffers_; }

private:
    mutable std::shared_mutex reg_mutex_;
    std::unordered_map<u16, std::unique_ptr<IModel>> models_;
    BufferRegistry buffers_;
    u16 next_cap_ = 1; // 0 reserved
};

} // namespace aicl
