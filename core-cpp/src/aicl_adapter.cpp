// =============================================================================
//  aicl_adapter.cpp
//  -----------------------------------------------------------------------------
//  AICLModelAdapter implementation. The adapter is the bridge between
//  AICL semantic dispatch (caller-side, typically the Rust core) and the
//  C++ model implementations.
//
//  Concurrency model:
//   - register / shutdown: exclusive (unique lock on mx_).
//   - handle_call / handle_stream / handle_cancel: concurrent-safe.
//   - Sessions are tracked for cancellation via weak_ptr.
// =============================================================================
#include <aicl/aicl_adapter.hpp>
#include <aicl/aicl_session.hpp>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <random>

namespace aicl {

namespace {
// Convert first 8 bytes of a Uuid to a u64 key for the session map.
u64 uuid_to_key(const Uuid& u) {
    u64 k = 0;
    for (std::size_t i = 0; i < 8; ++i) k = (k << 8) | u[i];
    return k;
}
} // namespace

// ---- Backend installation ---------------------------------------------------
void AICLModelAdapter::install_backend(BackendKind kind,
                                      const std::string& model_path, int n_ctx) {
    std::unique_lock<std::shared_mutex> lk(mx_);
    backend_ = make_backend(kind, model_path, n_ctx, 0);
    backend_kind_ = kind;
}

// ---- Model registration -----------------------------------------------------
u16 AICLModelAdapter::register_model(std::unique_ptr<IModel> model,
                                    const std::string& /* name */) {
    if (!model) return 0;
    {
        std::unique_lock<std::shared_mutex> lk(mx_);
        return ctx_.register_model(std::move(model));
    }
}

// ---- handle_call ------------------------------------------------------------
void AICLModelAdapter::handle_call(const ModelRequest& req, ModelResponse& out) {
    out = ModelResponse{};
    out.target = req.target;
    out.correlation_id = req.correlation_id;
    out.flags = AiclFlags(AiclFlags::RESPONSE);

    IModel* m = ctx_.lookup(req.target);
    if (!m) {
        out.error_code = AICL_E_NO_MODEL;
        out.error_message = "no model registered for cap_ref " + std::to_string(req.target);
        out.flags.set(AiclFlags::ERROR_FLAG);
        return;
    }
    auto session = std::make_shared<ModelSession>(m);
    session->begin(req.correlation_id, req.deadline_ms);
    session->set_active(true);
    {
        std::lock_guard<std::mutex> sk(sessions_mx_);
        sessions_[uuid_to_key(req.correlation_id)] = session;
    }
    auto t0 = std::chrono::steady_clock::now();
    try {
        m->invoke(req, out);
    } catch (const std::exception& e) {
        out.error_code = AICL_E_INTERNAL;
        out.error_message = e.what();
        out.flags.set(AiclFlags::ERROR_FLAG);
    }
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    (void)ms;
    session->set_active(false);
    {
        std::lock_guard<std::mutex> sk(sessions_mx_);
        sessions_.erase(uuid_to_key(req.correlation_id));
    }
    if (out.error_code != 0) out.flags.set(AiclFlags::ERROR_FLAG);
}

// ---- handle_stream ----------------------------------------------------------
void AICLModelAdapter::handle_stream(
    const ModelRequest& req,
    std::function<bool(const ModelResponse& chunk)> visitor) {
    if (!visitor) return;
    IModel* m = ctx_.lookup(req.target);
    if (!m) {
        ModelResponse err;
        err.target = req.target; err.correlation_id = req.correlation_id;
        err.error_code = AICL_E_NO_MODEL;
        err.error_message = "no model registered for cap_ref " + std::to_string(req.target);
        err.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::ERROR_FLAG);
        visitor(err); return;
    }
    auto wrapped = [&](const ModelResponse& chunk) -> bool {
        ModelResponse copy = chunk;
        copy.target = req.target; copy.correlation_id = req.correlation_id;
        if (!copy.flags.has(AiclFlags::STREAM_END) && !copy.flags.has(AiclFlags::ERROR_FLAG)) {
            copy.flags.set(AiclFlags::STREAM_CHUNK);
            copy.flags.set(AiclFlags::RESPONSE);
        }
        if (copy.error_code != 0) copy.flags.set(AiclFlags::ERROR_FLAG);
        return visitor(copy);
    };
    auto session = std::make_shared<ModelSession>(m);
    session->begin(req.correlation_id, req.deadline_ms);
    session->set_active(true);
    {
        std::lock_guard<std::mutex> sk(sessions_mx_);
        sessions_[uuid_to_key(req.correlation_id)] = session;
    }
    try {
        m->invoke_stream(req, wrapped);
    } catch (const std::exception& e) {
        ModelResponse err;
        err.target = req.target; err.correlation_id = req.correlation_id;
        err.error_code = AICL_E_INTERNAL; err.error_message = e.what();
        err.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_END | AiclFlags::ERROR_FLAG);
        visitor(err);
    }
    ModelResponse end;
    end.target = req.target; end.correlation_id = req.correlation_id;
    end.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_END);
    visitor(end);
    session->set_active(false);
    {
        std::lock_guard<std::mutex> sk(sessions_mx_);
        sessions_.erase(uuid_to_key(req.correlation_id));
    }
}

// ---- handle_cancel ----------------------------------------------------------
void AICLModelAdapter::handle_cancel(Uuid correlation_id) {
    std::shared_ptr<ModelSession> s;
    {
        std::lock_guard<std::mutex> sk(sessions_mx_);
        auto it = sessions_.find(uuid_to_key(correlation_id));
        if (it != sessions_.end()) s = it->second.lock();
    }
    if (s) { s->set_cancelled(true); s->cancel(); }
}

// ---- advertised_capabilities -----------------------------------------------
std::vector<std::string> AICLModelAdapter::advertised_capabilities() const {
    std::shared_lock<std::shared_mutex> lk(mx_);
    std::vector<std::string> out;
    for (u16 cap : ctx_.registered_caps()) {
        IModel* m = ctx_.lookup(cap);
        if (!m) continue;
        for (const auto& c : m->info().capabilities) {
            if (std::find(out.begin(), out.end(), c) == out.end()) out.push_back(c);
        }
    }
    return out;
}

// ---- report -----------------------------------------------------------------
ResourceUsage AICLModelAdapter::report() const {
    std::shared_lock<std::shared_mutex> lk(mx_);
    ResourceUsage agg;
    for (u16 cap : ctx_.registered_caps()) {
        IModel* m = ctx_.lookup(cap);
        if (!m) continue;
        ResourceUsage u = m->resources();
        agg.bytes_loaded += u.bytes_loaded;
        agg.kv_bytes += u.kv_bytes;
        agg.active_sessions += u.active_sessions;
        if (u.last_inference_ms > agg.last_inference_ms)
            agg.last_inference_ms = u.last_inference_ms;
    }
    return agg;
}

// ---- shutdown ---------------------------------------------------------------
void AICLModelAdapter::shutdown() {
    std::unique_lock<std::shared_mutex> lk(mx_);
    for (u16 cap : ctx_.registered_caps()) ctx_.unregister(cap);
    ctx_.buffers().clear();
    backend_.reset();
}

} // namespace aicl

