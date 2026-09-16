# =============================================================================
#  CMakeLists.txt — AICL Native C++ Integrations
#  -----------------------------------------------------------------------------
#  This directory contains native AI/model/hardware integrations:
#    - llama.cpp backend for GGUF model inference
#    - Hardware acceleration wrappers
#
#  These components integrate directly with native libraries (llama.cpp, etc.)
#  and expose a clean C++ interface to the core-cpp adapter layer.
#
#  Design philosophy:
#    - C++ owns native integration (llama.cpp, CUDA, etc.)
#    - Rust owns AICL protocol (no duplication)
#    - Zero-copy where possible (BufferRef, shared memory)
#
#  Usage:
#    cmake -B build -DCMAKE_BUILD_TYPE=Release -DAICL_WITH_LLAMA=ON
#    cmake --build build
#
#  Dependencies:
#    - llama.cpp (fetched via git submodule or external)
# =============================================================================

cmake_minimum_required(VERSION 3.20)
project(aicl_native_cpp VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- Options -----------------------------------------------------------------
option(AICL_WITH_LLAMA "Enable llama.cpp backend" ON)
option(AICL_FETCH_LLAMA "Fetch llama.cpp as submodule" OFF)

# llama.cpp path
if(AICL_WITH_LLAMA)
    if(NOT DEFINED AICL_LLAMA_PATH)
        # Try to find in common locations
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../llama.cpp")
            set(AICL_LLAMA_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../llama.cpp" CACHE PATH "llama.cpp directory")
        elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp")
            set(AICL_LLAMA_PATH "${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp" CACHE PATH "llama.cpp directory")
        endif()
    endif()

    if(AICL_LLAMA_PATH AND EXISTS ${AICL_LLAMA_PATH})
        message(STATUS "llama.cpp found at: ${AICL_LLAMA_PATH}")
    else()
        if(AICL_FETCH_LLAMA)
            message(STATUS "llama.cpp not found. To fetch it:")
            message(STATUS "  git submodule update --init --recursive")
            message(STATUS "  Or set AICL_LLAMA_PATH manually")
        endif()
    endif()
endif()

# ---- Compiler flags ----------------------------------------------------------
if(MSVC)
    add_compile_options(/W4 /WX- /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ---- Include directories ----------------------------------------------------
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# ---- llama.cpp backend library ----------------------------------------------
if(AICL_WITH_LLAMA AND AICL_LLAMA_PATH AND EXISTS ${AICL_LLAMA_PATH})
    set(AICL_LLAMA_SOURCES
        src/llama_backend.cpp
        src/llama_model.cpp
        src/llama_session.cpp
    )

    add_library(aicl_llama STATIC ${AICL_LLAMA_SOURCES})
    target_include_directories(aicl_llama PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${AICL_LLAMA_PATH}
        ${AICL_LLAMA_PATH}/common
    )
    target_link_libraries(aicl_llama PUBLIC
        llama
        common
    )

    target_compile_definitions(aicl_llama PUBLIC AICL_WITH_LLAMA=1)
    target_compile_definitions(aicl_native_cpp PUBLIC AICL_WITH_LLAMA=1)

    message(STATUS "llama.cpp backend: ENABLED")
else()
    message(STATUS "llama.cpp backend: DISABLED")
endif()

# ---- Installation ----------------------------------------------------------
include(GNUInstallDirs)

install(TARGETS aicl_llama
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(DIRECTORY include/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
