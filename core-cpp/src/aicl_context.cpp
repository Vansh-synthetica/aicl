// =============================================================================
//  aicl_context.cpp
//  -----------------------------------------------------------------------------
//  ModelContext is header-only (all methods are template-free and inline).
//  This translation unit exists as a stable link target.
// =============================================================================
#include <aicl/aicl_context.hpp>

namespace aicl {
namespace detail {
    inline volatile int aicl_context_translation_unit_anchor = 0;
}
} // namespace aicl
