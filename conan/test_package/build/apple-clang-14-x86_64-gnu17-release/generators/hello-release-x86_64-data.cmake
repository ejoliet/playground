########### AGGREGATED COMPONENTS AND DEPENDENCIES FOR THE MULTI CONFIG #####################
#############################################################################################

set(hello_COMPONENT_NAMES "")
set(hello_FIND_DEPENDENCY_NAMES "")

########### VARIABLES #######################################################################
#############################################################################################
set(hello_PACKAGE_FOLDER_RELEASE "/Users/ejoliet/.conan2/p/hello3a9a2940db2ff/p")
set(hello_BUILD_MODULES_PATHS_RELEASE )


set(hello_INCLUDE_DIRS_RELEASE "${hello_PACKAGE_FOLDER_RELEASE}/include")
set(hello_RES_DIRS_RELEASE )
set(hello_DEFINITIONS_RELEASE )
set(hello_SHARED_LINK_FLAGS_RELEASE )
set(hello_EXE_LINK_FLAGS_RELEASE )
set(hello_OBJECTS_RELEASE )
set(hello_COMPILE_DEFINITIONS_RELEASE )
set(hello_COMPILE_OPTIONS_C_RELEASE )
set(hello_COMPILE_OPTIONS_CXX_RELEASE )
set(hello_LIB_DIRS_RELEASE "${hello_PACKAGE_FOLDER_RELEASE}/lib")
set(hello_BIN_DIRS_RELEASE )
set(hello_LIBRARY_TYPE_RELEASE STATIC)
set(hello_IS_HOST_WINDOWS_RELEASE 0)
set(hello_LIBS_RELEASE hello)
set(hello_SYSTEM_LIBS_RELEASE )
set(hello_FRAMEWORK_DIRS_RELEASE )
set(hello_FRAMEWORKS_RELEASE )
set(hello_BUILD_DIRS_RELEASE )
set(hello_NO_SONAME_MODE_RELEASE FALSE)


# COMPOUND VARIABLES
set(hello_COMPILE_OPTIONS_RELEASE
    "$<$<COMPILE_LANGUAGE:CXX>:${hello_COMPILE_OPTIONS_CXX_RELEASE}>"
    "$<$<COMPILE_LANGUAGE:C>:${hello_COMPILE_OPTIONS_C_RELEASE}>")
set(hello_LINKER_FLAGS_RELEASE
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:${hello_SHARED_LINK_FLAGS_RELEASE}>"
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:${hello_SHARED_LINK_FLAGS_RELEASE}>"
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:${hello_EXE_LINK_FLAGS_RELEASE}>")


set(hello_COMPONENTS_RELEASE )