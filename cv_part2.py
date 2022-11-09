import os
#import serial
import numpy as np
from turtle import color
import matplotlib
# from Realsense.realsense_depth import *
# from Realsense.realsense import *
# from Algorithm.main import *
import cv2
import time
import argparse
import struct
#from UART.uart import uart_server
import torch
import pandas as pd

#Initialize CV Camera
class DepthCamera:
    print("here")
    # Constructor
    def __init__(self):
        # Configure depth and color streams
        self.pipeline = rs.pipeline()
        config = rs.config()

        # Get device product line for setting a supported resolution
        pipeline_wrapper = rs.pipeline_wrapper(self.pipeline)
        pipeline_profile = config.resolve(pipeline_wrapper)

        #Init streams
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        #Disable laser
        device = pipeline_profile.get_device()
        depth_sensor=device.query_sensors()[0]
        depth_sensor.set_option(rs.option.laser_power, 0)
        
        # Start streaming
        self.pipeline.start(config)

    # Get Depth and Color Frame
    def get_frame(self):
        try:
            frames = self.pipeline.wait_for_frames()
        except:
            return False, None, None
            
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()

        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        if not depth_frame or not color_frame:
            return False, None, None

        return True, depth_image, color_image

    def release(self):
        self.pipeline.stop()



#Make a CV capture class
# Make a struct to keep track of bounding boxes per robot (4 total plates per robot)



class Capture:
    # Constructor with depth camera
    def __init__(self, dc=None, camera_index=0, is_realsense=True):
        # Check if realsense class depth camera object is passed or an integer for the index of a regular camera
        self.is_realsense = is_realsense
        if is_realsense:
            if dc == None:
                self.dc = DepthCamera()
            else:
                self.dc = dc
        else:
            self.cap = cv2.VideoCapture(camera_index)
            self.is_realsense=False
            self.dc = None

        self.model = self.load_model()




    # Deconstructor
    def __del__(self):
        if self.is_realsense:
            self.dc.release()


    def load_model(self):
        # or yolov5m, yolov5l, yolov5x, custom
        return torch.hub.load('ultralytics/yolov5', 'custom',
                           path='./Algorithm/pt_files/best.pt')

    # Get Depth and Color Frame
    def capture_pipeline(self, debug=False, display=False):
        while True:
            # Get frame from camera
            ret = None
            if self.dc != None:
                ret, depth_image, color_image = self.dc.get_frame()
            else:
                ret, color_image = self.cap.read()

            if ret:
                key = cv2.waitKey(1)
                if key == 27:
                    break

                # Frame is valid
                self.process_frame(color_image=color_image, debug=debug, display=display)


    def is_blue(self, color_frame):

# 'HSV_LOWER_RED': (0, 20, 228),
#     'HSV_UPPER_RED': (18, 255, 254),
#     'HSV_LOWER_RED_2': (134, 0, 0),
#     'HSV_UPPER_RED_2': (255, 255, 251),
#     'HSV_LOWER_BLUE': (60, 30, 131),
#     'HSV_UPPER_BLUE': (121, 255, 255)

        blue_lower=np.array([60, 30, 131])
        blue_upper=np.array([121, 255, 255])
        hsv = cv2.cvtColor(color_frame, cv2.COLOR_BGR2HSV)
        blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
        blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        b_area = np.sum([cv2.contourArea(c) for c in blue_contours if (cv2.contourArea(c)) != 0])
        all_area = color_frame.shape[:2][0] *color_frame.shape[:2][1]
        if b_area> 0.19*all_area:
            return True
        else:
            return False
    # Process a color frame 
    def process_frame(self, color_image, debug=False, display=False):
        conf_thres = 0.25  # Confidence threshold
        # Get bounding boxes
        results = self.model(color_image)
        
        # Post process bounding boxes
        #rows = results.pandas().xyxy[0].to_numpy()

        detections_rows = results.pandas().xyxy


        
        rows = [elem.to_numpy() for elem in detections_rows][0]
        # for i in range(len(detections_rows)):
        #     rows = detections_rows[i].to_numpy()

        # Go through all detections

        for i in range(len(rows)):
            if len(rows) > 0:
                # Get the bounding box of the first object (most confident)
                x_min, y_min, x_max, y_max, conf, cls, label = rows[i]
                  # Coordinate system is as follows:
                  # 0,0 is the top left corner of the image
                  # x is the horizontal axis
                  # y is the vertical axis
                  # x_max, y_max is the bottom right corner of the screen
                  
                  # (0,0) --------> (x_max, 0)
                  # |               |
                  # |               |
                  # |               |
                  # |               |
                  # |               |
                  # (0, y_max) ----> (x_max, y_max)


                # if red plate, pass
                if not self.is_blue(color_frame=color_image[int(y_min):int(y_max), int(x_min):int(x_max)]):
                    continue
                if debug:
                    print("({},{}) \n\n\n                     ({},{})".format(x_min, y_min, x_max, y_max))
                    os.system('cls')
                    os.system('clear')

                # calculate angle offset, store as touple in anlges
                x_mid=round((x_max+x_min)/2-320,2)
                y_mid=round(-(y_max+y_min)/2+240,2)
                angles=[x_mid,y_mid]
                if display:
                    bbox = [x_min, y_min, x_max, y_max]
                    color_image = self.write_bbx_frame(color_image, bbox, label, conf, angles)
        # Display the image
        cv2.imshow('RealSense', color_image)
        cv2.waitKey(1)


    def write_bbx_frame(self, color_image, bbxs, label, conf, angle):
        # Display the bounding box
        x_min, y_min, x_max, y_max = bbxs
        cv2.rectangle(color_image, (int(x_min), int(y_min)), (int(
            x_max), int(y_max)), (0, 255, 0), 2)  # Draw with green color

        # Display the label with the confidence
        label_conf = label + " " + str(conf)
        cv2.putText(color_image, label_conf, (int(x_min), int(
            y_min)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)


        angle_x, angle_y = angle[0], angle[1]

        angle_str = "("+str(angle_x)+","+str(angle_y)+")"


        cv2.putText(color_image, angle_str, (int(x_max), int(
            y_max)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

        return color_image



stream = Capture(is_realsense=False, camera_index='./utils/vid.mp4')
stream.capture_pipeline(display=True, debug=True)