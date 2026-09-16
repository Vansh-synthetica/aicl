# Tests CMakeLists.txt
cmake_minimum_required(VERSION 3.20)

# Simple test executable
add_executable(aicl_core_test
    aicl_core_test.cpp
)
target_link_libraries(aicl_core_test PRIVATE aicl_core aicl_model_c)
target_include_directories(aicl_core_test PRIVATE
    ${CMAKE_SOURCE_DIR}/include
)

# Register test with CTest
add_test(NAME aicl_core_test COMMAND aicl_core_test)