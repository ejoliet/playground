########## MACROS ###########################################################################
#############################################################################################

# Requires CMake > 3.15
if(${CMAKE_VERSION} VERSION_LESS "3.15")
    message(FATAL_ERROR "The 'CMakeDeps' generator only works with CMake >= 3.15")
endif()

if(hello_FIND_QUIETLY)
    set(hello_MESSAGE_MODE VERBOSE)
else()
    set(hello_MESSAGE_MODE STATUS)
endif()

include(${CMAKE_CURRENT_LIST_DIR}/cmakedeps_macros.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/helloTargets.cmake)
include(CMakeFindDependencyMacro)

check_build_type_defined()

foreach(_DEPENDENCY ${hello_FIND_DEPENDENCY_NAMES} )
    # Check that we have not already called a find_package with the transitive dependency
    if(NOT ${_DEPENDENCY}_FOUND)
        find_dependency(${_DEPENDENCY} REQUIRED ${${_DEPENDENCY}_FIND_MODE})
    endif()
endforeach()

set(hello_VERSION_STRING "1.0")
set(hello_INCLUDE_DIRS ${hello_INCLUDE_DIRS_RELEASE} )
set(hello_INCLUDE_DIR ${hello_INCLUDE_DIRS_RELEASE} )
set(hello_LIBRARIES ${hello_LIBRARIES_RELEASE} )
set(hello_DEFINITIONS ${hello_DEFINITIONS_RELEASE} )

# Only the first installed configuration is included to avoid the collision
foreach(_BUILD_MODULE ${hello_BUILD_MODULES_PATHS_RELEASE} )
    message(${hello_MESSAGE_MODE} "Conan: Including build module from '${_BUILD_MODULE}'")
    include(${_BUILD_MODULE})
endforeach()


