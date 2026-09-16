// =============================================================================
//  aicl_session.cpp
//  -----------------------------------------------------------------------------
//  ModelSession is abstract; per-backend implementations live in their
//  respective translation units. The base class is header-only.
// =============================================================================
#include <aicl/aicl_session.hpp>

namespace aicl {
namespace detail {
    inline volatile int aicl_session_translation_unit_anchor = 0;
}
} // namespace aicl
