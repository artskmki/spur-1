#!/usr/bin/env python
# -*- coding: utf-8 -*-
#####
#####
# This script is copied from https://github.com/arebgun/dynamixel_motor/pull/27
#####
#####
#
# Software License Agreement (BSD License)
#
# Copyright (c) 2015, Kei Okada.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Kei Okada nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from threading import Thread

import rospy

from sensor_msgs.msg import JointState

class JointStatePublisher():
    def __init__(self, controller_namespace, controllers):
        self.update_rate = 1000
        self.state_update_rate = 50
        self.trajectory = []
        
        self.controller_namespace = controller_namespace
        self.joint_names = [c.joint_name for c in controllers]
        self.pre_position = []
        self.abs_position = []

        self.joint_to_controller = {}
        for c in controllers:
             self.joint_to_controller[c.joint_name] = c
            
        self.port_to_joints = {}
        for c in controllers:
            if c.port_namespace not in self.port_to_joints: self.port_to_joints[c.port_namespace] = []
            self.port_to_joints[c.port_namespace].append(c.joint_name)
            
        self.port_to_io = {}
        for c in controllers:
            if c.port_namespace in self.port_to_io: continue
            self.port_to_io[c.port_namespace] = c.dxl_io

    def initialize(self):
        self.msg = JointState()
        return True


    def start(self):
        self.running = True
        self.state_pub = rospy.Publisher('joint_states', JointState , queue_size=100)

        Thread(target=self.update_state).start()


    def stop(self):
        self.running = False

    def update_state(self):
        rate = rospy.Rate(self.state_update_rate)
        while self.running and not rospy.is_shutdown():
            self.msg.header.stamp = rospy.Time.now()
            self.msg.name = []
            self.msg.position = []
            self.msg.velocity = []
            self.msg.effort = []
            
            i = 0
            for port, joints in self.port_to_joints.items():
                vals = []
                rospy.logdebug("joints : "+" ".join(joints))
                for joint in joints:
                    j = self.joint_names.index(joint)
                    
                    motor_id = self.joint_to_controller[joint].motor_id
                    co = self.joint_to_controller[joint]
                    io = self.port_to_io[port]
                    rospy.logdebug("port={} id={}, {}".format(port, motor_id, joint))

                    self.msg.name.append(joint)
                    po = ve = ef = 0
                    try:
                        ret = io.get_feedback(motor_id)
                        if len(self.abs_position) == 0:
                            po = self.raw_to_rad_pos(ret['position'],co)
                        else:
                            if (ret['position'] - self.pre_position[i]) < -3072:
                                self.abs_position[i] = self.abs_position[i] + (ret['position'] - self.pre_position[i] + 4096)
                            elif  (ret['position'] - self.pre_position[i]) > 3072:
                                self.abs_position[i] = self.abs_position[i] + (ret['position'] - self.pre_position[i] - 4096)
                            else:
                                self.abs_position[i] = self.abs_position[i] + (ret['position'] - self.pre_position[i])
                            self.pre_position[i] = ret['position']
                            po = self.raw_to_rad_pos(self.abs_position[i],co)
                        ve = self.raw_to_rad_spd(ret['speed'],co)
                        ef = self.raw_to_rad_spd(ret['load'],co)
                        #po = self.raw_to_rad_pos(io.get_position(motor_id),co)
                        #ve = self.raw_to_rad_spd(io.get_speed(motor_id),co)
                        #ef = io.get_current(motor_id)
                    except Exception as e:
                        rospy.logerr(e)
                    self.msg.position.append(po)
                    self.msg.velocity.append(ve)
                    self.msg.effort.append(ef)
                    i += 1

            # initialize pre_position and abs_position
            if len(self.pre_position) != len(self.msg.position):
                self.pre_position = [0]*len(self.msg.position)
                self.abs_position = [0]*len(self.msg.position)
                i = 0
                for port, joints in self.port_to_joints.items():
                    for joint in joints:
                        j = self.joint_names.index(joint)
                        motor_id = self.joint_to_controller[joint].motor_id
                        io = self.port_to_io[port]
                        ret = io.get_feedback(motor_id)
                        self.pre_position[i] = ret['position']
                        self.abs_position[i] = ret['position']
                        i+= 1

            self.state_pub.publish(self.msg)
            rate.sleep()

    def raw_to_rad_pos(self, raw, c):
        return (c.initial_position_raw - raw if c.flipped else raw - c.initial_position_raw) * c.RADIANS_PER_ENCODER_TICK
    def raw_to_rad_spd(self, raw, c):
        return (- raw if c.flipped else raw ) * c.RADIANS_PER_ENCODER_TICK
