// =============================================================================
//  aicl_value.hpp
//  -----------------------------------------------------------------------------
//  Value representation for the AICL (Adaptive Inter-Module Communication
//  Language) C++ model adapter layer.
//
//  This header mirrors the Rust `Operand` enum defined in
//      core-rust/src/aicl/operand.rs
//  The two representations must stay binary-compatible at the FFI boundary
//  (see csrc/aicl_model_c.c for the C ABI shim).
//
//  -----------------------------------------------------------------------------
//  Copy semantics
//  -----------------------------------------------------------------------------
//  - `Value` itself is a small tagged union. Copying a `Value` copies at most
//    ~64 bytes of discriminant+payload (tag + max inline scalar), which is
//    cheap. Never copy a `Value` expecting zero overhead; use `std::move` if
//    you intend to consume it.
//  - `Value::Bytes` holds a `std::shared_ptr<std::vector<uint8_t>>`. The
//    *byte data* is therefore reference-counted and shared, never copied,
//    between Values and Buffers. The 16-byte `BufferRef` descriptor is the
//    zero-copy wire form.
//  - `Value::Str` is `std::string` and is deep-copied on `Value` copy.
//  - `Value::List` and `Value::Map` are deep-copied on `Value` copy. The
//    contained Bytes entries still share their backing buffer via shared_ptr.
//  - `Value::Tensor` shares its data via `BufferRef` (i.e. a 16-byte handle
//    into `BufferRegistry`). The shape vector is deep-copied. Tensor memory
//    itself is NEVER copied when moving a `Tensor` around; only the handle.
//
//  -----------------------------------------------------------------------------
//  Zero-copy path
//  -----------------------------------------------------------------------------
//      caller  --register(std::shared_ptr)-> BufferRegistry  --BufferRef--> IModel
//                                                                            |
//                                                                            v
//                                                                       IModel::invoke
//                                                                            |
//                                                                            v
//                                                              ModelResponse (with
//                                                              BufferRef descriptors
//                                                              + Tensor handles)
// =============================================================================
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <typeinfo>
#include <utility>
#include <vector>

namespace aicl {

// ---- Type aliases ----------------------------------------------------------
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

using Uuid   = std::array<u8, 16>;   ///< 128-bit correlation id, matches Rust Uuid
using CapRef = u16;                  ///< Model capability reference (registry index)
using BytesBuffer = std::vector<u8>; ///< Owning byte vector (shared via shared_ptr)

// ---- Forward declarations --------------------------------------------------
struct Value;
struct Tensor;
struct BufferRef;
struct AiclFlags;
struct ModelRequest;
struct ModelResponse;
struct Embedding;

using ValueList = std::vector<Value>;
using ValueMap  = std::map<std::string, Value>;

// ---- Tensor dtype ----------------------------------------------------------
/**
 * @brief Numeric element type of a `Tensor`.
 *
 * Numeric values are chosen to match the AICL wire protocol so the C++ side
 * can cast directly without translation.
 */
enum class DType : u16 {
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
    Unknown = 0xFFFF,
};

/** @brief Return size in bytes of one element of the given dtype, or 0 if unknown. */
constexpr std::size_t dtype_size(DType d) noexcept {
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
        default:          return 0;
    }
}

/** @brief Stringify a dtype for debugging / error messages. */
inline const char* dtype_name(DType d) noexcept {
    switch (d) {
        case DType::F32:  return "F32";
        case DType::F16:  return "F16";
        case DType::BF16: return "BF16";
        case DType::I8:   return "I8";
        case DType::I16:  return "I16";
        case DType::I32:  return "I32";
        case DType::I64:  return "I64";
        case DType::U8:   return "U8";
        case DType::U16:  return "U16";
        case DType::U32:  return "U32";
        case DType::F64:  return "F64";
        default:          return "Unknown";
    }
}

// ---- BufferRef -------------------------------------------------------------
/**
 * @brief 16-byte descriptor for a slice of a buffer in `BufferRegistry`.
 *
 * A `BufferRef` is the *only* form in which tensor/embedding byte data crosses
 * module boundaries. The bytes themselves live in a `BufferRegistry` and are
 * shared by `std::shared_ptr`. The descriptor can be freely copied.
 */
struct BufferRef {
    u64 id     = 0;       ///< Buffer registry id (must be non-zero).
    u32 offset = 0;       ///< Byte offset into the buffer.
    u32 length = 0;       ///< Byte length of the slice.

    constexpr BufferRef() noexcept = default;
    constexpr BufferRef(u64 id_, u32 offset_, u32 length_) noexcept
        : id(id_), offset(offset_), length(length_) {}

    constexpr bool is_valid() const noexcept {
        return id != 0 && length != 0;
    }
};

// ---- Tensor ----------------------------------------------------------------
/**
 * @brief N-dim tensor view backed by an external `BufferRef`.
 *
 * Tensor data is *not* owned by the `Tensor`; the actual bytes live in a
 * `BufferRegistry` referenced by `data`. Moving or copying a `Tensor` only
 * copies the 16-byte `BufferRef` and the small shape vector.
 */
struct Tensor {
    DType            dtype = DType::Unknown;
    std::vector<i64> shape;   ///< Dimension sizes, e.g. {1, 3, 224, 224}.
    BufferRef        data;    ///< Slice into BufferRegistry.

    constexpr Tensor() noexcept = default;
    Tensor(DType dt, std::vector<i64> sh, BufferRef br)
        : dtype(dt), shape(std::move(sh)), data(br) {}

    /// @brief Number of elements implied by the shape (0 if any dim is 0).
    std::size_t numel() const noexcept {
        if (shape.empty()) return 0;
        std::size_t n = 1;
        for (i64 s : shape) {
            if (s <= 0) return 0;
            n *= static_cast<std::size_t>(s);
        }
        return n;
    }

    /// @brief Required byte size to hold this tensor (numel * dtype_size).
    std::size_t byte_size() const noexcept {
        const std::size_t es = dtype_size(dtype);
        if (es == 0) return 0;
        return numel() * es;
    }
};

// ---- Embedding -------------------------------------------------------------
/**
 * @brief Token/embedding pair produced by an embedding model.
 *
 * Both `token_ids` and `scores` reference shared buffers (no copy of the data
 * itself). The two `BufferRef`s are *independent* — they may point to the
 * same backing buffer or different ones.
 */
struct Embedding {
    BufferRef token_ids;   ///< Token id sequence (dtype = I32 or U32).
    BufferRef scores;      ///< Per-token score / logit buffer.
    u32       num_tokens = 0;
    DType     dtype      = DType::F32;
};

// ---- AiclFlags -------------------------------------------------------------
/**
 * @brief 16-bit flags mirrored from Rust `AiclFlags`.
 *
 * Layout matches the wire format. Constants are bit positions, not masks.
 */
struct AiclFlags {
    u16 bits = 0;

    static constexpr u16 REQUEST        = 0x0001;
    static constexpr u16 RESPONSE       = 0x0002;
    static constexpr u16 STREAM_CHUNK   = 0x0004;
    static constexpr u16 STREAM_END     = 0x0008;
    static constexpr u16 ERROR_FLAG     = 0x0010;
    static constexpr u16 CANCEL         = 0x0020;
    static constexpr u16 HAS_BUFFER_REF = 0x2000;

    constexpr AiclFlags() noexcept = default;
    constexpr explicit AiclFlags(u16 b) noexcept : bits(b) {}

    constexpr bool has(u16 mask) const noexcept { return (bits & mask) != 0; }
    constexpr void set(u16 mask) noexcept { bits |= mask; }
    constexpr void clear(u16 mask) noexcept { bits &= static_cast<u16>(~mask); }
};

// ---- Value tagged union ----------------------------------------------------
/**
 * @brief Tagged union of all AICL operand kinds.
 *
 * Construct via the `Make_*` factory functions; access via `as_*` methods.
 * A default-constructed `Value` is `Null`.
 */
struct Value {
    enum class Kind : u16 {
        Null       = 0,
        Bool       = 1,
        I8         = 2,
        I16        = 3,
        I32        = 4,
        I64        = 5,
        U8         = 6,
        U16        = 7,
        U32        = 8,
        U64        = 9,
        F32        = 10,
        F64        = 11,
        Str        = 12,
        Bytes      = 13,
        Uuid       = 14,
        Handle     = 15,
        CapRef     = 16,
        BufRef     = 17,
        List       = 18,
        Map        = 19,
        TsMs       = 20,
        DurationMs = 21,
        Tensor     = 22,
    };

    Kind kind = Kind::Null;

    union {
        bool       b;
        i8         i8v;
        i16        i16v;
        i32        i32v;
        i64        i64v;
        u8         u8v;
        u16        u16v;
        u32        u32v;
        u64        u64v;
        f32        f32v;
        f64        f64v;
        Uuid       uuidv;
        BufferRef  buf;
    } u{};

    std::string                    str;
    std::shared_ptr<BytesBuffer>   bytes;
    ValueList                      list;
    ValueMap                       map;
    Tensor                         tensor;

    Value() noexcept = default;
    Value(const Value& o) { copy_from(o); }
    Value(Value&& o) noexcept { move_from(std::move(o)); }
    Value& operator=(const Value& o) { if (this != &o) copy_from(o); return *this; }
    Value& operator=(Value&& o) noexcept {
        if (this != &o) { reset(); move_from(std::move(o)); } return *this;
    }
    ~Value() = default;

    void reset() noexcept {
        kind = Kind::Null;
        u = {};
        str.clear();
        bytes.reset();
        list.clear();
        map.clear();
        tensor = {};
    }

private:
    void copy_from(const Value& o) {
        reset();
        kind  = o.kind;
        u     = o.u;
        str   = o.str;
        bytes = o.bytes;
        list  = o.list;
        map   = o.map;
        tensor = o.tensor;
    }
    void move_from(Value&& o) noexcept {
        kind  = o.kind;
        u     = o.u;
        str   = std::move(o.str);
        bytes = std::move(o.bytes);
        list  = std::move(o.list);
        map   = std::move(o.map);
        tensor = std::move(o.tensor);
        o.reset();
    }

public:
    // -- Factories ----------------------------------------------------------
    static Value Make_Null()        { Value v; return v; }
    static Value Make_Bool(bool x)  { Value v; v.kind = Kind::Bool; v.u.b = x; return v; }
    static Value Make_I8(i8 x)      { Value v; v.kind = Kind::I8;   v.u.i8v = x; return v; }
    static Value Make_I16(i16 x)    { Value v; v.kind = Kind::I16;  v.u.i16v = x; return v; }
    static Value Make_I32(i32 x)    { Value v; v.kind = Kind::I32;  v.u.i32v = x; return v; }
    static Value Make_I64(i64 x)    { Value v; v.kind = Kind::I64;  v.u.i64v = x; return v; }
    static Value Make_U8(u8 x)      { Value v; v.kind = Kind::U8;   v.u.u8v = x; return v; }
    static Value Make_U16(u16 x)    { Value v; v.kind = Kind::U16;  v.u.u16v = x; return v; }
    static Value Make_U32(u32 x)    { Value v; v.kind = Kind::U32;  v.u.u32v = x; return v; }
    static Value Make_U64(u64 x)    { Value v; v.kind = Kind::U64;  v.u.u64v = x; return v; }
    static Value Make_F32(f32 x)    { Value v; v.kind = Kind::F32;  v.u.f32v = x; return v; }
    static Value Make_F64(f64 x)    { Value v; v.kind = Kind::F64;  v.u.f64v = x; return v; }
    static Value Make_Str(std::string s) { Value v; v.kind = Kind::Str; v.str = std::move(s); return v; }
    static Value Make_Bytes(std::shared_ptr<BytesBuffer> p) {
        Value v; v.kind = Kind::Bytes; v.bytes = std::move(p); return v;
    }
    static Value Make_Bytes(std::vector<u8> b) {
        auto p = std::make_shared<BytesBuffer>(std::move(b));
        return Make_Bytes(std::move(p));
    }
    static Value Make_Uuid(const Uuid& x)  { Value v; v.kind = Kind::Uuid; v.u.uuidv = x; return v; }
    static Value Make_Handle(u64 x)        { Value v; v.kind = Kind::Handle; v.u.u64v = x; return v; }
    static Value Make_CapRef(CapRef x)     { Value v; v.kind = Kind::CapRef; v.u.u16v = x; return v; }
    static Value Make_BufRef(BufferRef x)  { Value v; v.kind = Kind::BufRef; v.u.buf = x; return v; }
    static Value Make_TsMs(i64 x)          { Value v; v.kind = Kind::TsMs; v.u.i64v = x; return v; }
    static Value Make_DurationMs(i64 x)    { Value v; v.kind = Kind::DurationMs; v.u.i64v = x; return v; }
    static Value Make_List(ValueList l)    { Value v; v.kind = Kind::List; v.list = std::move(l); return v; }
    static Value Make_Map(ValueMap m)      { Value v; v.kind = Kind::Map;  v.map  = std::move(m);  return v; }
    static Value Make_Tensor(Tensor t)     { Value v; v.kind = Kind::Tensor; v.tensor = std::move(t); return v; }

    // -- Convenience factory aliases (lowercase for ergonomic use) ----------
    static Value from_bool(bool x)    { return Make_Bool(x); }
    static Value from_i32(i32 x)      { return Make_I32(x); }
    static Value from_i64(i64 x)      { return Make_I64(x); }
    static Value from_u32(u32 x)      { return Make_U32(x); }
    static Value from_u64(u64 x)      { return Make_U64(x); }
    static Value from_f32(f32 x)      { return Make_F32(x); }
    static Value from_f64(f64 x)      { return Make_F64(x); }
    static Value from_string(std::string s) { return Make_Str(std::move(s)); }
    static Value from_json(const std::string& s) { return Make_Str(s); }

    // -- Typed accessors (throw std::bad_cast on type mismatch)
    bool   as_bool()   const { if (kind != Kind::Bool)  throw std::bad_cast(); return u.b; }
    i8     as_i8()     const { if (kind != Kind::I8)    throw std::bad_cast(); return u.i8v; }
    i16    as_i16()    const { if (kind != Kind::I16)   throw std::bad_cast(); return u.i16v; }
    i32    as_i32()    const { if (kind != Kind::I32)   throw std::bad_cast(); return u.i32v; }
    i64    as_i64()    const { if (kind != Kind::I64)   throw std::bad_cast(); return u.i64v; }
    u8     as_u8()     const { if (kind != Kind::U8)    throw std::bad_cast(); return u.u8v; }
    u16    as_u16()    const { if (kind != Kind::U16)   throw std::bad_cast(); return u.u16v; }
    u32    as_u32()    const { if (kind != Kind::U32)   throw std::bad_cast(); return u.u32v; }
    u64    as_u64()    const { if (kind != Kind::U64)   throw std::bad_cast(); return u.u64v; }
    f32    as_f32()    const { if (kind != Kind::F32)   throw std::bad_cast(); return u.f32v; }
    f64    as_f64()    const { if (kind != Kind::F64)   throw std::bad_cast(); return u.f64v; }
    const std::string&                as_str()    const { if (kind != Kind::Str)    throw std::bad_cast(); return str; }
    const std::shared_ptr<BytesBuffer>& as_bytes() const { if (kind != Kind::Bytes)  throw std::bad_cast(); return bytes; }
    const Uuid&     as_uuid()   const { if (kind != Kind::Uuid)   throw std::bad_cast(); return u.uuidv; }
    u64             as_handle() const { if (kind != Kind::Handle)  throw std::bad_cast(); return u.u64v; }
    CapRef          as_capref() const { if (kind != Kind::CapRef) throw std::bad_cast(); return u.u16v; }
    BufferRef       as_bufref() const { if (kind != Kind::BufRef) throw std::bad_cast(); return u.buf; }
    const ValueList& as_list()   const { if (kind != Kind::List)   throw std::bad_cast(); return list; }
    const ValueMap&  as_map()    const { if (kind != Kind::Map)    throw std::bad_cast(); return map; }
    const Tensor&    as_tensor() const { if (kind != Kind::Tensor) throw std::bad_cast(); return tensor; }
    i64              as_ts()     const { if (kind != Kind::TsMs)    throw std::bad_cast(); return u.i64v; }
    i64              as_dur()    const { if (kind != Kind::DurationMs) throw std::bad_cast(); return u.i64v; }

    // -- Soft accessors (return default without throwing)
    bool try_bool(bool default_ = false) const noexcept { return kind == Kind::Bool ? u.b : default_; }
    i32  try_i32(i32 default_ = 0)        const noexcept { return kind == Kind::I32 ? u.i32v : default_; }
    i64  try_i64(i64 default_ = 0)        const noexcept { return kind == Kind::I64 ? u.i64v : default_; }
    f32  try_f32(f32 default_ = 0.0f)     const noexcept { return kind == Kind::F32 ? u.f32v : default_; }
    const std::string& try_str(const std::string& default_ = empty_string()) const noexcept {
        return kind == Kind::Str ? str : default_;
    }
    static const std::string& empty_string() { static const std::string s; return s; }
    bool is_null() const noexcept { return kind == Kind::Null; }
};

// ---- ModelRequest ----------------------------------------------------------
/**
 * @brief Single inference call from the AICL runtime into the model.
 *
 * Inputs are passed as a `ValueMap` (string -> Value). Heavy payload is
 * referenced via `input_buffers` (zero-copy). The `flags` field carries
 * the AICL frame flags (REQUEST, STREAM_*, etc.).
 */
struct ModelRequest {
    CapRef    target = 0;
    Uuid      correlation_id{};
    u32       deadline_ms = 0;
    ValueMap  inputs;
    std::vector<BufferRef> input_buffers;
    AiclFlags flags;
};

// ---- ModelResponse ---------------------------------------------------------
/**
 * @brief Result of a model invocation.
 *
 * `outputs` mirrors `inputs`; `output_buffers` is a parallel set of descriptors
 * for byte payloads (token streams, embedding matrices, etc.). On streaming
 * `flags` has `STREAM_CHUNK` set for each token and `STREAM_END` for the last.
 */
struct ModelResponse {
    CapRef    target = 0;
    Uuid      correlation_id{};
    u32       error_code  = 0;
    std::string error_message;
    ValueMap  outputs;
    std::vector<BufferRef> output_buffers;
    AiclFlags flags;
};

} // namespace aicl



