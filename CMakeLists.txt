cmake_minimum_required(VERSION 3.20.0)
project(rqt_uav_gcs_traj)

find_package(catkin REQUIRED COMPONENTS rospy rqt_gui rqt_gui_py)

catkin_package()

catkin_python_setup()

catkin_install_python(PROGRAMS scripts/rqt_uav_gcs_traj DESTINATION
                      ${CATKIN_PACKAGE_BIN_DESTINATION})

install(FILES plugin.xml DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
