# =============================================================================
#  CMakeLists.txt — AICL Core C++ Adapter
#  -----------------------------------------------------------------------------
#  Build configuration for the C++ model adapter layer.
#  This produces:
#    - aicl_core       : C++ library (static)
#    - aicl_model_c    : C shim library (for Rust FFI)
#
#  Usage:
#    cmake -B build -DCMAKE_BUILD_TYPE=Release
#    cmake --build build
#
#  Options:
#    AICL_WITH_LLAMA      : Enable llama.cpp backend (default: OFF)
#    AICL_LLAMA_PATH     : Path to llama.cpp source (if AICL_WITH_LLAMA=ON)
#    AICL_BUILD_EXAMPLES  : Build example programs (default: ON)
# =============================================================================

cmake_minimum_required(VERSION 3.20)
project(aicl_core_cpp VERSION 1.0.0 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile_commands.json for tooling
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ---- Options -----------------------------------------------------------------
option(AICL_WITH_LLAMA     "Enable llama.cpp backend"   OFF)
option(AICL_BUILD_EXAMPLES "Build example programs"       ON)

if(AICL_WITH_LLAMA)
    message(STATUS "llama.cpp backend: ENABLED")
    if(NOT AICL_LLAMA_PATH)
        # Try common paths
        find_path(_llama_common NAMES llama.h PATH_SUFFIXES include PATHS
            /usr/local/include
            /usr/include
            $ENV{HOME}/llama.cpp
            $ENV{USERPROFILE}/llama.cpp
        )
        if(_llama_common)
            set(AICL_LLAMA_PATH ${_llama_common} CACHE PATH "llama.cpp include directory")
        endif()
    endif()
else()
    message(STATUS "llama.cpp backend: DISABLED (set AICL_WITH_LLAMA=ON to enable)")
endif()

# ---- Compiler flags ----------------------------------------------------------
if(MSVC)
    add_compile_options(/W4 /WX- /permissive-)
    # Disable specific warnings
    add_compile_options(/wd4251)  # DLL interface
    add_compile_options(/wd4275)  # non-DLL interface
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror=return-type)
    add_compile_options(-fno-exceptions)  # For no_std compatibility
endif()

# ---- Include directories ----------------------------------------------------
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/csrc
)

# ---- Source files -----------------------------------------------------------
set(CORE_SOURCES
    src/aicl_adapter.cpp
    src/aicl_buffer.cpp
    src/aicl_context.cpp
    src/aicl_session.cpp
    src/aicl_value.cpp
    src/aicl_model.cpp          # Backend factory and implementations
)

set(C_SOURCES
    csrc/aicl_model_c.cpp       # C ABI shim
)

# ---- Library: aicl_core (C++) ----------------------------------------------
add_library(aicl_core STATIC ${CORE_SOURCES})
target_include_directories(aicl_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(aicl_core PROPERTIES
    OUTPUT_NAME aicl_core
    POSITION_INDEPENDENT_CODE ON
)

# ---- Library: aicl_model_c (C shim) -----------------------------------------
add_library(aicl_model_c STATIC ${C_SOURCES})
target_include_directories(aicl_model_c PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(aicl_model_c PRIVATE aicl_core)
set_target_properties(aicl_model_c PROPERTIES
    OUTPUT_NAME aicl_model_c
    POSITION_INDEPENDENT_CODE ON

# ---- Shared memory transport source ------------------------------------------
list(APPEND CORE_SOURCES src/aicl_shm.cpp)
list(APPEND C_SOURCES csrc/aicl_shm.c)
)

# ---- Optional: llama.cpp backend --------------------------------------------
if(AICL_WITH_LLAMA AND EXISTS ${AICL_LLAMA_PATH})
    # Create a library from llama.cpp source
    # This assumes llama.cpp is available as source
    message(STATUS "llama.cpp path: ${AICL_LLAMA_PATH}")
    
    # Define the backend compilation unit with llama support
    set(AICL_LLAMA_SOURCES
        src/aicl_llama_backend.cpp
    )
    
    add_library(aicl_llama_backend STATIC ${AICL_LLAMA_SOURCES})
    target_include_directories(aicl_llama_backend PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${AICL_LLAMA_PATH}
    )
    target_link_libraries(aicl_llama_backend PRIVATE aicl_core)
    
    # Link both libraries to model_c when llama is enabled
    target_link_libraries(aicl_model_c PRIVATE aicl_llama_backend)
    
    target_compile_definitions(aicl_core PRIVATE AICL_WITH_LLAMA=1)
    target_compile_definitions(aicl_model_c PRIVATE AICL_WITH_LLAMA=1)
endif()

# ---- Examples ---------------------------------------------------------------
if(AICL_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# ---- Installation ----------------------------------------------------------
include(GNUInstallDirs)

install(TARGETS aicl_core aicl_model_c
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(DIRECTORY include/aicl
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(FILES include/aicl_model.h
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

# ---- Testing ----------------------------------------------------------------
enable_testing()
add_subdirectory(tests)
