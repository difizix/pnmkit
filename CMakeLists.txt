# Require CMake 3.15+ (matching scikit-build-core)
cmake_minimum_required(VERSION 3.15...4.0)

# Disable C++20 module dependency scanning
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)

# Project setup
if(NOT DEFINED SKBUILD_PROJECT_NAME)
  set(SKBUILD_PROJECT_NAME "pnmkit")
endif()
if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.0.0")
endif()

project(
  ${SKBUILD_PROJECT_NAME}
  VERSION ${SKBUILD_PROJECT_VERSION}
  LANGUAGES CXX)

# Find Python early
find_package(
  Python
  COMPONENTS Interpreter Development.Module
  REQUIRED)

# --- Dependencies ---
include(FetchContent)
set(FETCH_LIST "")

# pybind11
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
  FetchContent_Declare(
    pybind11
    URL https://github.com/pybind/pybind11/archive/refs/tags/v3.0.1.tar.gz)
  list(APPEND FETCH_LIST pybind11)
endif()

# OpenMP
if(APPLE)
  if(NOT DEFINED OpenMP_ROOT AND DEFINED ENV{OpenMP_ROOT})
    set(OpenMP_ROOT $ENV{OpenMP_ROOT})
  endif()
  find_package(OpenMP QUIET)
  if(NOT OpenMP_FOUND)
    set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp")
    find_library(
      OMP_LIB
      NAMES omp
      PATHS "${OpenMP_ROOT}/lib" "/opt/homebrew/opt/libomp/lib"
            "/usr/local/opt/libomp/lib")
    if(OMP_LIB)
      set(OpenMP_FOUND TRUE)
      add_library(OpenMP::OpenMP_CXX UNKNOWN IMPORTED)
      set_target_properties(
        OpenMP::OpenMP_CXX
        PROPERTIES IMPORTED_LOCATION "${OMP_LIB}"
                   INTERFACE_COMPILE_OPTIONS "${OpenMP_CXX_FLAGS}"
                   INTERFACE_LINK_LIBRARIES "${OMP_LIB}")
    endif()
  endif()
endif()
if(NOT OpenMP_FOUND)
  find_package(OpenMP REQUIRED)
endif()

# image3kit (as requested by user)
FetchContent_Declare(
  image3kit
  GIT_REPOSITORY https://github.com/image3kit/image3kit.git
  GIT_TAG main)
list(APPEND FETCH_LIST image3kit)

# Make requested dependencies available
if(FETCH_LIST)
  set(CMAKE_WARN_DEPRECATED
      OFF
      CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(${FETCH_LIST})
  set(CMAKE_WARN_DEPRECATED
      ON
      CACHE BOOL "" FORCE)
endif()

# --- Main Target ---
python_add_library(pnmkit_core MODULE src/main.cpp WITH_SOABI)
set_target_properties(pnmkit_core PROPERTIES OUTPUT_NAME _pnmkit)

target_link_libraries(
  pnmkit_core PRIVATE pybind11::headers image3kit_headers
                      Python::Module OpenMP::OpenMP_CXX)

target_compile_definitions(pnmkit_core PRIVATE VERSION_INFO=${PROJECT_VERSION})
set_property(TARGET pnmkit_core PROPERTY CXX_STANDARD 23)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(MSVC)
  target_compile_options(pnmkit_core PRIVATE /openmp:llvm /diagnostics:caret
                                             /bigobj)
  target_compile_definitions(pnmkit_core PRIVATE NOMINMAX)
else()
  target_compile_options(pnmkit_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Installation
install(TARGETS pnmkit_core DESTINATION pnmkit)
install(DIRECTORY src/pnmkit/ DESTINATION pnmkit)
