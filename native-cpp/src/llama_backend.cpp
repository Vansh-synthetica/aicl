// =============================================================================
//  llama_backend.cpp — llama.cpp GGUF model implementation
//  -----------------------------------------------------------------------------
//  Implements IModel interface using llama.cpp for GGUF inference.
//
//  Features:
//    - Loads GGUF models via llama.cpp
//    - Supports CPU and GPU inference
//    - Provides streaming via callbacks
//    - Manages KV cache per-context
// =============================================================================
#include "llama_backend.hpp"

#ifdef AICL_WITH_LLAMA
#include <llama.h>
#endif

#include <aicl/aicl_value.hpp>
#include <algorithm>
#include <chrono>
#include <cstring>

namespace aicl {
namespace llama {

static const int MAX_TOKENS_DEFAULT = 512;

LlamaModel::LlamaModel(const LlamaConfig& config, const ModelInfo& info)
    : config_(config), info_(info) {
    if (!load_model() || !init_context()) {
        unload();
    }
}

LlamaModel::~LlamaModel() { unload(); }

bool LlamaModel::load_model() {
#ifdef AICL_WITH_LLAMA
    llama_model_params params = llama_model_default_params();
    params.n_ctx = config_.n_ctx;
    params.n_gpu_layers = config_.n_gpu_layers;

    model_ = llama_load_model_from_file(config_.model_path.c_str(), params);
    if (!model_) return false;

    info_.context_length = llama_n_ctx(model_);
    info_.gpu = config_.n_gpu_layers > 0;
    return true;
#else
    (void)config_; return false;
#endif
}

bool LlamaModel::init_context() {
#ifdef AICL_WITH_LLAMA
    llama_context_params params = llama_context_default_params();
    params.n_ctx = config_.n_ctx;
    params.n_threads = config_.n_threads > 0 ? config_.n_threads : 4;
    context_ = llama_new_context_with_model(model_, params);
    return context_ != nullptr;
#else
    return false;
#endif
}

void LlamaModel::unload() {
#ifdef AICL_WITH_LLAMA
    if (context_) { llama_free(context_); context_ = nullptr; }
    if (model_) { llama_free_model(model_); model_ = nullptr; }
#endif
}

void LlamaModel::invoke(const ModelRequest& req, ModelResponse& out) {
    out = ModelResponse{};
    out.target = req.target;
    out.correlation_id = req.correlation_id;
    out.flags = AiclFlags(AiclFlags::RESPONSE);

    if (!is_loaded()) {
        out.error_code = 1;
        out.error_message = "model not loaded";
        out.flags.set(AiclFlags::ERROR_FLAG);
        return;
    }

    std::string prompt;
    auto it = req.inputs.find("prompt");
    if (it != req.inputs.end()) prompt = it->second.as_str();

    auto t0 = std::chrono::steady_clock::now();

    std::string result;
    int tokens = 0;
    auto on_token = [&](const std::string& token, bool) -> bool {
        result += token;
        tokens++;
        return tokens < MAX_TOKENS_DEFAULT;
    };

    generate_impl(prompt, on_token, req.correlation_id);

    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    out.outputs["text"] = Value::from_string(result);
    out.outputs["tokens"] = Value::from_i32(tokens);
    out.outputs["time_ms"] = Value::from_f64(ms);
    out.outputs["model"] = Value::from_string(info_.id);
    usage_.last_inference_ms = ms;
}

void LlamaModel::invoke_stream(const ModelRequest& req,
                              std::function<bool(const ModelResponse& chunk)> visitor) {
    if (!is_loaded()) {
        ModelResponse err;
        err.target = req.target;
        err.correlation_id = req.correlation_id;
        err.error_code = 1;
        err.error_message = "model not loaded";
        err.flags = AiclFlags(AiclFlags::ERROR_FLAG);
        visitor(err);
        return;
    }

    std::string prompt;
    auto it = req.inputs.find("prompt");
    if (it != req.inputs.end()) prompt = it->second.as_str();

    int tokens_generated = 0;
    auto t0 = std::chrono::steady_clock::now();

    auto on_token = [&](const std::string& token, bool eos) -> bool {
        ModelResponse chunk;
        chunk.target = req.target;
        chunk.correlation_id = req.correlation_id;
        chunk.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_CHUNK);
        chunk.outputs["token"] = Value::from_string(token);

        if (eos || tokens_generated >= MAX_TOKENS_DEFAULT) {
            chunk.flags = AiclFlags(AiclFlags::RESPONSE | AiclFlags::STREAM_END);
            auto t1 = std::chrono::steady_clock::now();
            double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
            chunk.outputs["total_tokens"] = Value::from_i32(tokens_generated);
            chunk.outputs["time_ms"] = Value::from_f64(ms);
        }
        tokens_generated++;
        return visitor(chunk);
    };

    generate_impl(prompt, on_token, req.correlation_id);
    usage_.last_inference_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - t0).count();
}

void LlamaModel::cancel(Uuid) {}

ResourceUsage LlamaModel::resources() const {
    ResourceUsage usage = usage_;
#ifdef AICL_WITH_LLAMA
    if (model_) usage.bytes_loaded = llama_model_size(model_);
    if (context_) usage.kv_bytes = llama_state_get_size(context_);
#endif
    return usage;
}

std::string LlamaModel::generate_impl(
    const std::string& prompt,
    std::function<bool(const std::string&, bool)> on_token,
    Uuid /*correlation_id*/) {

#ifdef AICL_WITH_LLAMA
    if (!context_ || !model_) return "";

    // Tokenize prompt
    auto tokens = llama_tokenize(model_, prompt.c_str(), true);
    if (tokens.empty()) tokens.push_back(llama_token_bos());

    for (size_t i = 0; i < tokens.size(); ++i) {
        if (llama_eval(context_, &tokens[i], 1, i, config_.n_threads) != 0) {
            llama_free(context_);
            init_context();
            return "";
        }
    }

    std::string output;
    int n_ctx = llama_n_ctx(model_);
    int n_cur = static_cast<int>(tokens.size());

    while (true) {
        auto logits = llama_get_logits(context_);
        auto n_vocab = llama_n_vocab(model_);

        int next_token = 0;
        float max_logit = -1e9f;
        for (int i = 0; i < n_vocab; ++i) {
            if (logits[i] > max_logit) { max_logit = logits[i]; next_token = i; }
        }

        bool is_eos = llama_token_is_eog(model_, next_token);

        char buf[256];
        int len = llama_token_to_piece(model_, next_token, buf, sizeof(buf), 0, true);
        if (len > 0) {
            std::string token_str(buf, len);
            output += token_str;
            if (!on_token(token_str, is_eos)) break;
        }

        if (is_eos) break;
        if (n_cur >= n_ctx - 1) break;

        if (llama_eval(context_, &next_token, 1, n_cur, config_.n_threads) != 0) break;
        n_cur++;
    }

    llama_free(context_);
    init_context();
    return output;
#else
    (void)prompt; (void)on_token;
    return "";
#endif
}

std::unique_ptr<IModel> load_llama_model(const std::string& path,
                                          const ModelInfo& overrides,
                                          const LlamaConfig& config) {
    LlamaConfig cfg = config;
    cfg.model_path = path;

    ModelInfo info = overrides;
    if (info.id.empty()) info.id = "llama-model";
    if (info.family.empty()) info.family = "llama";
    if (info.capabilities.empty()) {
        info.capabilities = {"text.generate", "text.embed"};
    }

    auto model = std::make_unique<LlamaModel>(cfg, info);
    if (!model->is_loaded()) return nullptr;
    return model;
}

std::unique_ptr<IModel> load_llama_model(const std::string& path,
                                          const ModelInfo& overrides) {
    return load_llama_model(path, overrides, {});
}

} // namespace llama
} // namespace aicl
