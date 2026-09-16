// aicl_tensor.hpp — Tensor descriptor and embedding types.
//
// Copy semantics:
// - Tensor is a *view* into a buffer registered in BufferRegistry.
//   Creating a Tensor struct copies ~20 bytes; the underlying data is NOT copied.
// - Embedding is similarly a view: {ids, scores} where both are BufferRefs.
// - Ownership of the backing buffer belongs to the BufferRegistry (or the
//   caller that registered it). The Tensor just borrows.

#pragma once

#include "aicl_types.hpp"

namespace aicl {

// ---------------------------------------------------------------------------
// Tensor descriptor
// ---------------------------------------------------------------------------

enum class DType : u8 {
    F32  = 0,
    F16  = 1,
    BF16 = 2,
    I8   = 3,
    I16  = 4,
    I32  = 5,
    I64  = 6,
    U8   = 7,
    U16  = 8,
    U32  = 9,
    F64  = 10,
};

inline std::size_t dtype_size(DType d) {
    switch (d) {
        case DType::F32:  return 4;
        case DType::F16:  return 2;
        case DType::BF16: return 2;
        case DType::I8:   return 1;
        case DType::I16:  return 2;
        case DType::I32:  return 4;
        case DType::I64:  return 8;
        case DType::U8:   return 1;
        case DType::U16:  return 2;
        case DType::U32:  return 4;
        case DType::F64:  return 8;
    }
    return 0;
}

// A tensor view: dtype, shape, and the underlying buffer reference.
// The actual numeric data lives in the BufferRegistry pointed to by `data`.
struct Tensor {
    DType                 dtype   = DType::F32;
    std::vector<i64>      shape;  // e.g. {1, 512, 4096}
    BufferRef             data{}; // points to a registered buffer

    // Total element count from shape.
    std::size_t num_elements() const {
        std::size_t n = 1;
        for (auto d : shape) n *= static_cast<std::size_t>(d);
        return n;
    }

    // Total byte size.
    std::size_t byte_size() const {
        return num_elements() * dtype_size(dtype);
    }
};

// ---------------------------------------------------------------------------
// Embedding result
// ---------------------------------------------------------------------------

// An embedding: a vector of float32 scores, indexed by token id.
// Both fields are BufferRefs — zero-copy views into registered buffers.
struct Embedding {
    BufferRef token_ids;  // u32 array,  length = num_tokens
    BufferRef scores;     // f32 array,  length = num_tokens
    u32       num_tokens = 0;
    DType     dtype      = DType::F32;
};

} // namespace aicl
