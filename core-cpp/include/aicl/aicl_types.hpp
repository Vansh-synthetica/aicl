// aicl_types.hpp — C++ value types that mirror AICL operand semantics.
//
// Design notes
// ------------
// * This header is *C++-only* (not C). It mirrors the Rust `Operand` enum
//   and adds tensor/embedding types that the C side actually uses.
// * `Value` is a tagged union (variant) covering scalars, strings, bytes,
//   arrays, maps, and tensor descriptors.
// * Large buffers are passed by reference (`BufferRef`) and never copied
//   unless the caller explicitly asks for a copy. See `aicl_buffer.hpp`.
// * Zero-copy: `Value::Bytes` and `Value::Tensor` carry a `BufferRef`
//   pointing into a shared arena — see `BufferRegistry`.

#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace aicl {

// ---------------------------------------------------------------------------
// Scalar types
// ---------------------------------------------------------------------------

using i8  = std::int8_t;
using i16 = std::int16_t;
using i32 = std::int32_t;
using i64 = std::int64_t;
using u8  = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using f32 = float;
using f64 = double;

// 16-byte UUID.
using Uuid = std::array<u8, 16>;

// 8-byte opaque handle.
using Handle = u64;

// 2-byte big-endian capability reference.
using CapRef = u16;

// ---------------------------------------------------------------------------
// Buffer reference (zero-copy descriptor)
//
// `id` identifies a registered buffer in the `BufferRegistry`.
// `offset`/`length` describe a view into that buffer.
// ---------------------------------------------------------------------------

struct BufferRef {
    u64 id      = 0;
    u32 offset  = 0;
    u32 length  = 0;
};

} // namespace aicl
