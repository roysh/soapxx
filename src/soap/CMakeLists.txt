file(GLOB LOCAL_SOURCES *.cpp)

# SUBDIRECTORIES
add_subdirectory(base)
add_subdirectory(linalg)
add_subdirectory(linalg/permanent)
add_subdirectory(tools)
add_subdirectory(soapy)
add_subdirectory(external)

# COMPILE SOURCES
get_directory_property(LINALG_LOCAL_SOURCES DIRECTORY linalg DEFINITION LOCAL_SOURCES)
get_directory_property(BASE_LOCAL_SOURCES DIRECTORY base DEFINITION LOCAL_SOURCES)
set(LOCAL_SOURCES ${LOCAL_SOURCES} ${LINALG_LOCAL_SOURCES} ${BASE_LOCAL_SOURCES})
message("Sources: soap/")
foreach(item ${LOCAL_SOURCES})
    message(STATUS " o " ${item})
endforeach()
message("Headers: soap/")
foreach(item ${HEADERS})
    message(STATUS " o " ${item})
endforeach()

# COMPILE LIBRARIES
set(LD_LIBRARIES ${Boost_LIBRARIES} ${PYTHON_LIBRARIES} ${MPI_LIBRARIES})
get_directory_property(LINALG_LD_LIBRARIES DIRECTORY linalg DEFINITION LINALG_LIBRARIES)
set(LD_LIBRARIES ${LD_LIBRARIES} ${LINALG_LD_LIBRARIES})

add_library(_soapxx ${LOCAL_SOURCES})
target_link_libraries(_soapxx ${LD_LIBRARIES})
set_target_properties(_soapxx PROPERTIES PREFIX "" SUFFIX ".so" LIBRARY_OUTPUT_DIRECTORY .)

configure_file(SOAPRC.in SOAPRC @ONLY)

install(TARGETS _soapxx LIBRARY DESTINATION ${LOCAL_INSTALL_DIR})
install(FILES __init__.py ${CMAKE_CURRENT_BINARY_DIR}/SOAPRC DESTINATION ${LOCAL_INSTALL_DIR})

# HEADERS
file(GLOB HEADERS *.hpp)
install(FILES ${HEADERS} DESTINATION ${LOCAL_INSTALL_DIR}/include/soap)
#install(DIRECTORY linalg DESTINATION ${LOCAL_INSTALL_DIR})
