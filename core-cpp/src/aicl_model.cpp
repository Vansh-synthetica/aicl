// =============================================================================
//  aicl_model.cpp — Backend factory and Dummy model implementation
//  -----------------------------------------------------------------------------
//  Concrete implementations of IModelBackend and IModel.
//
//  This file contains:
//    - DummyBackend / DummyModel: test implementation (always available)
//    - make_backend() / load_model() factory functions
//
//  llama.cpp integration is in aicl_llama_backend.cpp (when AICL_WITH_LLAMA=1).
// =============================================================================
#include <aicl/aicl_backend.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>

#include <chrono>
#include <cstring>
#include <random>
#include <sstream>

namespace aicl {

// ============================================================================
// Dummy Backend
// ============================================================================

class DummyBackend final : public IModelBackend {
public:
    DummyBackend() = default;
    ~DummyBackend() override = default;

    std::string name() const override { return "dummy"; }
    std::string version() const override { return "1.0.0"; }

    bool supports_capability(const std::string& cap) const override {
        return cap == "text.generate" ||
               cap == "text.embed" ||
               cap == "text.classify";
    }

    std::vector<std::string> capabilities() const override {
        return {"text.generate", "text.embed", "text.classify"};
    }
};

// ============================================================================
// Dummy Model
// ============================================================================

class DummyModel final : public IModel {
public:
    explicit DummyModel(const ModelInfo& info) : info_(info) {}
    ~DummyModel() override = default;

    const ModelInfo& info() const override { return info_; }
    ResourceUsage resources() const override { return usage_; }

    void invoke(const ModelRequest& req, ModelResponse& out) override {
        out = ModelResponse{};
        out.target = req.target;
        out.correlation_id = req.correlation_id;
        out.flags = AiclFlags(AiclFlags::RESPONSE);

        auto t0 = std::chrono::steady_clock::now();

        std::string prompt = extract_string(req.inputs, "prompt");
        std::string response = generate_echo(prompt);

        out.outputs["text"] = Value::from_string(response);
        out.outputs["model"] = Value::from_string(info_.id);
        out.outputs["tokens_used"] = Value::from_u32(static_cast<u32>(response.size()));

        auto t1 = std::chrono::steady_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        usage_.last_inference_ms = ms;
        usage_.bytes_loaded = 0;
    }

    void invoke_stream(const ModelRequest& req,
                      std::function<bool(const ModelResponse& chunk)> visitor) override {
        ModelResponse chunk = {};
        chunk.target = req.target;
        chunk.correlation_id = req.correlation_id;
        chunk.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_CHUNK);

        std::string prompt = extract_string(req.inputs, "prompt");

        for (char c : prompt) {
            chunk.outputs.clear();
            std::string token(1, c);
            chunk.outputs["token"] = Value::from_string(token);
            if (!visitor(chunk)) return;
        }

        chunk.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_END);
        chunk.outputs.clear();
        chunk.outputs["eos"] = Value::from_bool(true);
        visitor(chunk);
    }

    void cancel(Uuid correlation_id) override {}

private:
    ModelInfo info_;
    mutable ResourceUsage usage_{};

    static std::string extract_string(const ValueMap& inputs, const std::string& key) {
        auto it = inputs.find(key);
        if (it != inputs.end()) return it->second.as_str();
        return "";
    }

    static std::string generate_echo(const std::string& input) {
        if (input.empty()) {
            return "Hello! I'm a dummy model. Send a prompt to get an echo response.";
        }
        std::ostringstream oss;
        oss << "Echo: \"" << input << "\" (processed by dummy model)";
        return oss.str();
    }
};
// ============================================================================
// Model Factory
// ============================================================================

std::unique_ptr<IModelBackend> make_backend(BackendKind kind,
                                             const std::string& model_path,
                                             int n_ctx,
                                             int n_threads) {
    switch (kind) {
        case BackendKind::Dummy:
            return std::make_unique<DummyBackend>();
        case BackendKind::LlamaCpp:
#ifdef AICL_WITH_LLAMA
            return make_llama_backend(model_path, n_ctx, n_threads);
#else
            return nullptr;
#endif
        default:
            return nullptr;
    }
}

std::unique_ptr<IModel> load_model(BackendKind kind,
                                    const std::string& path,
                                    const ModelInfo& overrides) {
    ModelInfo info = overrides;
    if (info.id.empty()) {
        info.id = "model-" + std::to_string(
            std::chrono::steady_clock::now().time_since_epoch().count() % 10000);
    }
    if (info.family.empty()) {
        info.family = "unknown";
    }
    if (info.capabilities.empty()) {
        info.capabilities = {"text.generate"};
    }

    switch (kind) {
        case BackendKind::Dummy:
            return std::make_unique<DummyModel>(info);
#ifdef AICL_WITH_LLAMA
        case BackendKind::LlamaCpp:
            return load_llama_model(path, info);
#endif
        default:
            return nullptr;
    }
}

} // namespace aicl
