// =============================================================================
//  aicl_model.hpp
//  -----------------------------------------------------------------------------
//  AICL-aware model interface. Wraps an IModelBackend with a single
//  `invoke` / `invoke_stream` / `cancel` entry point using the AICL
//  ModelRequest/ModelResponse protocol.
//
//  This is the C++ peer of the Rust core's `Model` trait. The same
//  semantics apply: a model is a registered capability (CapRef) that
//  the runtime can dispatch calls to.
// =============================================================================
#pragma once

#include <aicl/aicl_backend.hpp>
#include <aicl/aicl_value.hpp>

#include <cstddef>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace aicl {

/** @brief Static, descriptive metadata about a loaded model. */
struct ModelInfo {
    std::string                id;             ///< User-chosen model id (e.g. "llama-3-8b-instruct").
    std::string                family;         ///< Family name (e.g. "llama", "qwen2", "phi3").
    std::vector<std::string>   capabilities;   ///< e.g. {"text.generate", "text.embed"}.
    std::size_t                context_length = 0;
    std::size_t                embedding_dim  = 0;
    bool                       gpu = false;
};

/** @brief Live resource usage snapshot for diagnostics. */
struct ResourceUsage {
    std::size_t bytes_loaded     = 0;   ///< Bytes of model weights resident in RAM/VRAM.
    std::size_t kv_bytes         = 0;   ///< Bytes of KV cache currently allocated.
    std::size_t active_sessions  = 0;   ///< Number of currently open ModelSession instances.
    double      last_inference_ms = 0.0;///< Wall-time of most recent inference (ms).
};

/**
 * @brief Per-model AICL dispatch interface.
 *
 * Implementations are produced by `load_model(...)` for a given backend.
 * They are NOT thread-safe internally — protect with a mutex at the call
 * site if needed (the adapter layer does this).
 */
class IModel {
public:
    virtual ~IModel() = default;

    /// @brief Static, immutable model info.
    virtual const ModelInfo& info() const = 0;

    /// @brief Non-streaming call. Fills `out` with a single ModelResponse.
    virtual void invoke(const ModelRequest& req, ModelResponse& out) = 0;

    /// @brief Streaming call. The visitor returns true to keep going, false
    ///        to cancel. The visitor is called once per token chunk and a
    ///        final time with STREAM_END set.
    virtual void invoke_stream(
        const ModelRequest& req,
        std::function<bool(const ModelResponse& chunk)> visitor) = 0;

    /// @brief Cancel an in-flight call identified by correlation id.
    virtual void cancel(Uuid correlation_id) = 0;

    /// @brief Snapshot of current resource usage.
    virtual ResourceUsage resources() const = 0;
};

/**
 * @brief Load a model from a file using the chosen backend.
 *
 * The returned `IModel` owns its resources; destroying it releases the
 * model weights. `overrides` allows the caller to patch family /
 * capabilities / context_length etc. on the resulting `ModelInfo`.
 */
std::unique_ptr<IModel> load_model(
    BackendKind kind,
    const std::string& path,
    const ModelInfo& overrides = {});

} // namespace aicl
