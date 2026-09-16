// =============================================================================
//  aicl_backend.hpp
//  -----------------------------------------------------------------------------
//  Abstract backend interface and factory.
//
//  A backend is the *transport* to a model runtime (dummy, llama.cpp, remote).
//  It does not know about AICL semantics; it just loads models and answers
//  capability queries. Higher layers (aicl_model.hpp) wrap it with the AICL
//  ModelRequest/ModelResponse protocol.
//
//  Compile-guarded: when AICL_WITH_LLAMA is not defined, only Dummy is built.
// =============================================================================
#pragma once

#include <memory>
#include <string>
#include <vector>

namespace aicl {

/** @brief Which backend implementation to use. */
enum class BackendKind : int {
    Dummy     = 0,
    LlamaCpp  = 1,
};

/**
 * @brief Common interface for any model backend.
 *
 * Backends answer: "what is your name, what can you do, which capabilities
 * does a given model expose?". They do NOT know about AICL ModelRequest /
 * ModelResponse; that protocol is layered above.
 */
class IModelBackend {
public:
    virtual ~IModelBackend() = default;

    /// @brief Human-readable backend name, e.g. "dummy", "llama.cpp".
    virtual std::string name() const = 0;

    /// @brief Backend version string (vendor-defined).
    virtual std::string version() const = 0;

    /// @brief Does this backend support the given named capability?
    ///        Capabilities are short strings like "text.generate",
    ///        "text.embed", "image.classify", etc.
    virtual bool supports_capability(const std::string& name) const = 0;

    /// @brief Return the list of capabilities this backend can advertise.
    virtual std::vector<std::string> capabilities() const = 0;
};

/**
 * @brief Construct a backend of the requested kind.
 *
 * @param kind       Backend kind (Dummy or LlamaCpp).
 * @param model_path Path to a model file (LlamaCpp only; ignored otherwise).
 * @param n_ctx      Context length (LlamaCpp; default 2048).
 * @param n_threads  Thread count (0 = hardware_concurrency; LlamaCpp only).
 * @return unique_ptr to the constructed backend, or nullptr on failure.
 */
std::unique_ptr<IModelBackend> make_backend(
    BackendKind kind,
    const std::string& model_path = {},
    int n_ctx = 2048,
    int n_threads = 0);

} // namespace aicl
