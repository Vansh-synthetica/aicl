// =============================================================================
//  aicl_session.hpp
//  -----------------------------------------------------------------------------
//  Per-call session state: KV cache, sampling state, token history.
//  A `ModelSession` is a short-lived object created per inference call.
//  Different backends may subclass this to carry their internal session state.
// =============================================================================
#pragma once

#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>

namespace aicl {

/**
 * @brief Per-inference session state.
 *
 * Represents a single request's KV cache and sampler. Short-lived: created at
 * the start of a request, destroyed (or reset) when done. The base class
 * is abstract; backends subclass it with their own session data.
 */
class ModelSession {
public:
    /**
     * @brief Construct a session for a given model.
     * @param model Pointer to the owning model (must outlive this session).
     */
    explicit ModelSession(IModel* model) : model_(model) {}
    virtual ~ModelSession() = default;

    ModelSession(const ModelSession&) = delete;
    ModelSession& operator=(const ModelSession&) = delete;

    /// @brief Begin a new inference session with a correlation id and deadline.
    virtual void begin(const Uuid& correlation_id, u32 deadline_ms) = 0;

    /// @brief Feed one token id (for streaming prefill phase).
    virtual void feed_token(u32 token_id) = 0;

    /// @brief Generate one token. Returns false at EOS.
    ///        `out_logprob` is the log probability of the chosen token.
    virtual bool generate_one(u32& out_token, f32& out_logprob) = 0;

    /// @brief Cancel the current session.
    virtual void cancel() = 0;

    /// @brief End the session and return resource usage.
    virtual ResourceUsage end() = 0;

    /// @brief Current resource usage snapshot.
    virtual ResourceUsage resources() const = 0;

    /// @brief Is this session currently active (not cancelled, not ended)?
    bool active() const noexcept { return active_.load(std::memory_order_acquire); }
    void set_active(bool v) noexcept { active_.store(v, std::memory_order_release); }

    /// @brief Is this session cancelled?
    bool cancelled() const noexcept { return cancelled_.load(std::memory_order_acquire); }
    void set_cancelled(bool v) noexcept { cancelled_.store(v, std::memory_order_release); }

    /// @brief Correlation id of this session.
    const Uuid& correlation_id() const noexcept { return correlation_id_; }

protected:
    IModel* model_ = nullptr;
    Uuid correlation_id_{};
    std::atomic<bool> active_{false};
    std::atomic<bool> cancelled_{false};
    mutable std::mutex mx_; // protects backend-specific state
};

} // namespace aicl
