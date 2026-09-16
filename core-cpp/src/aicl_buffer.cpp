// =============================================================================
//  aicl_buffer.cpp
//  -----------------------------------------------------------------------------
//  BufferRegistry is header-only (no template specialisation needed).
//  This translation unit exists as a stable link target and to allow future
//  instrumentation (memory accounting, eviction, etc.) without recompiling
//  all consumers.
// =============================================================================
#include <aicl/aicl_buffer.hpp>

namespace aicl {
namespace detail {
    inline volatile int aicl_buffer_translation_unit_anchor = 0;
}
} // namespace aicl
