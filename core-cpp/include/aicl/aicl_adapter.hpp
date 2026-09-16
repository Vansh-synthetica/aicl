// =============================================================================
//  aicl_adapter.hpp
//  -----------------------------------------------------------------------------
//  The top-level C++ adapter: bridges the AICL semantic layer to the
//  C++ model layer. The Rust core holds the AICL protocol; this class
//  answers `handle_call` and `handle_stream` by dispatching to a
//  `ModelContext`.
//
//  Typical lifetime:
//      AICLModelAdapter adapter;
//      adapter.install_backend(BackendKind::Dummy);
//      auto cap = adapter.register_model(make_unique<DummyModel>(), "echo");
//      ModelRequest req;  req.target = cap; ...
//      ModelResponse out;
//      adapter.handle_call(req, out);
// =============================================================================
#pragma once

#include <aicl/aicl_backend.hpp>
#include <aicl/aicl_context.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_session.hpp>
#include <aicl/aicl_value.hpp>

#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace aicl {

/**
 * @brief The main AICL <-> C++ model bridge.
 *
 * This is the C++ peer of the Rust core's `AiclRuntime`. The Rust side
 * drives the protocol; this class exposes the high-level `handle_*` calls
 * that protocol frames get translated into.
 */
class AICLModelAdapter {
public:
    AICLModelAdapter() = default;
    ~AICLModelAdapter() { shutdown(); }

    AICLModelAdapter(const AICLModelAdapter&) = delete;
    AICLModelAdapter& operator=(const AICLModelAdapter&) = delete;

    // ---- Backend / model lifecycle ---------------------------------------

    /**
     * @brief Install a backend implementation. The backend is used as the
     *        default for any subsequent `load_model` call. The backend
     *        itself does not own models; it is just a factory.
     */
    void install_backend(BackendKind kind,
                         const std::string& model_path = "",
                         int n_ctx = 2048);

    /**
     * @brief Register an already-constructed `IModel` and return a CapRef.
     *
     * The adapter takes ownership of `model`. `name` is a convenience
     * label recorded in the model's `ModelInfo::id` if it is empty.
     */
    u16 register_model(std::unique_ptr<IModel> model, const std::string& name = "");

    // ---- Request dispatch -------------------------------------------------

    /**
     * @brief Execute a single non-streaming inference call.
     *
     * Translates `req` -> `out`. On lookup failure sets `out.error_code`
     * (model_error) and a message; never throws on a missing model.
     */
    void handle_call(const ModelRequest& req, ModelResponse& out);

    /**
     * @brief Execute a streaming inference call. The visitor is called once
     *        per generated token with `STREAM_CHUNK` set, and a final time
     *        with `STREAM_END` set. Returning false from the visitor cancels
     *        further generation.
     */
    void handle_stream(const ModelRequest& req,
                       std::function<bool(const ModelResponse& chunk)> visitor);

    /// @brief Cancel any in-flight call with the given correlation id.
    void handle_cancel(Uuid correlation_id);

    // ---- Introspection ----------------------------------------------------

    /// @brief Aggregate the set of capabilities of all loaded models.
    std::vector<std::string> advertised_capabilities() const;

    /// @brief Access the underlying model context (mutable).
    ModelContext&       context()       { return ctx_; }
    const ModelContext& context() const { return ctx_; }

    /// @brief Sum of resource usage across all registered models.
    ResourceUsage report() const;

    /// @brief Release all loaded models and clear the buffer arena.
    void shutdown();

private:
    // Backend factory state (one default backend; per-model backends are
    // stored inside their own IModel).
    std::unique_ptr<IModelBackend> backend_;
    BackendKind backend_kind_ = BackendKind::Dummy;

    ModelContext ctx_;
    mutable std::shared_mutex mx_;

    // Per-correlation-id sessions for cancellation.
    mutable std::mutex sessions_mx_;
    std::unordered_map<u64, std::weak_ptr<ModelSession>> sessions_;
};

} // namespace aicl
