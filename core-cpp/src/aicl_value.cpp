// =============================================================================
//  aicl_value.cpp
//  -----------------------------------------------------------------------------
//  Implementation of any non-trivial Value operations. Most of `Value` is
//  header-only (the tagged union is small enough). This translation unit
//  exists so that ABI consumers and the C shim have a stable link target.
//
//  Currently this file is mostly a placeholder; the C ABI shim
//  (csrc/aicl_model_c.c) uses Value as an opaque type via inline helpers.
// =============================================================================
#include <aicl/aicl_value.hpp>

namespace aicl {

// Reserve a translation unit so static analyzers and version scripts have
// something to attach to. No behaviour is implemented here yet; all
// Value construction and access lives in aicl_value.hpp.
namespace detail {
    inline volatile int aicl_value_translation_unit_anchor = 0;
}

} // namespace aicl
