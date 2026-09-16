// =============================================================================
//  llama_backend.hpp — llama.cpp GGUF inference backend
//  -----------------------------------------------------------------------------
//  Integrates llama.cpp for local GGUF model inference.
//
//  Design:
//    - Wraps llama.cpp's C API (llama.h)
//    - Exposes IModelBackend interface from core-cpp
//    - Supports CPU and GPU inference
//    - Zero-copy buffer passing where possible
//
//  Limitations:
//    - Current implementation uses synchronous inference
//    - Streaming is implemented via callbacks
//    - KV cache is managed per-session
//
//  Thread-safety:
//    - llama.cpp models are NOT thread-safe by default
//    - Each model instance should be protected by a mutex at the adapter level
// =============================================================================
#pragma once

#include <aicl/aicl_backend.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>
#include <aicl/aicl_buffer.hpp>

#include <memory>
#include <mutex>
#include <string>
#include <vector>

// Forward declarations for llama.cpp types
struct llama_context;
struct llama_model;

namespace aicl {
namespace llama {

// ============================================================================
// Types
// ============================================================================

/** @brief llama.cpp backend configuration */
struct LlamaConfig {
    std::string model_path;      // Path to GGUF file
    int n_ctx = 2048;            // Context length
    int n_threads = 0;           // Threads (0 = auto)
    int n_gpu_layers = 0;        // GPU layers (0 = CPU only)
    float rope_freq_base = 0.0f; // RoPE base frequency
    float rope_freq_scale = 1.0f;// RoPE frequency scale
    float temperature = 0.8f;   // Sampling temperature
    int32_t seed = -1;          // Random seed (-1 = random)
};

/** @brief Sampling parameters */
struct SamplingParams {
    float temperature = 0.8f;
    float top_p = 0.95f;
    float top_k = 40;
    float repeat_penalty = 1.1f;
    int repeat_penalty_tokens = 64;
};

/** @brief Generation result */
struct GenerationResult {
    std::string text;
    int tokens_generated = 0;
    double inference_time_ms = 0.0;
};

// ============================================================================
// LlamaModel — llama.cpp model wrapper
// ============================================================================

class LlamaModel : public IModel {
public:
    explicit LlamaModel(const LlamaConfig& config, const ModelInfo& info);
    ~LlamaModel() override;

    // IModel interface
    const ModelInfo& info() const override { return info_; }
    void invoke(const ModelRequest& req, ModelResponse& out) override;
    void invoke_stream(const ModelRequest& req,
                      std::function<bool(const ModelResponse& chunk)> visitor) override;
    void cancel(Uuid correlation_id) override;
    ResourceUsage resources() const override;

    // llama-specific methods
    const LlamaConfig& config() const { return config_; }
    bool is_loaded() const { return model_ != nullptr; }

private:
    LlamaConfig config_;
    ModelInfo info_;
    SamplingParams sampling_;

    // llama.cpp handles (owned)
    llama_model* model_ = nullptr;
    llama_context* context_ = nullptr;

    mutable std::mutex mutex_;
    mutable ResourceUsage usage_;

    bool load_model();
    bool init_context();
    void unload();

    std::string generate_impl(const std::string& prompt,
                             std::function<bool(const std::string&, bool)> on_token,
                             Uuid correlation_id);
};

// ============================================================================
// Factory
// ============================================================================

/** @brief Create a LlamaModel from a GGUF file */
std::unique_ptr<IModel> load_llama_model(const std::string& path,
                                         const ModelInfo& overrides,
                                         const LlamaConfig& config = {});

/** @brief Create a LlamaModel with default config */
std::unique_ptr<IModel> load_llama_model(const std::string& path,
                                         const ModelInfo& overrides);

} // namespace llama
} // namespace aicl
