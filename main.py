"""
Credit for API logic goes to https://github.com/radiance-project/ear-web
"""

# Standard library imports
import os
import signal
import sys
import threading
import time

# Third-party imports
import bluetooth
import eel
from dotenv import load_dotenv
import numpy as np
import psutil
from PyQt5.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
    QRegion
)
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget
)

# Expose decorator from eel
from eel import expose
load_dotenv()

# Add signal class
class SignalEmitter(QObject):
    show_overlay = pyqtSignal()

# Function to toggle visibility
def toggle_window(action):
    # Ensure Electron process is running
    for proc in psutil.process_iter(['pid', 'name']):
        if 'electron' in proc.info['name']:
            break
    else:
        print("Electron process not running")
        return

    # Send action (hide/show) to Electron
    expose(action)


class EarX:
    def __init__(self, overlay):
        self.TARGET_MAC = os.getenv("EARBUD_MAC_ADDRESS")
        if not self.TARGET_MAC:
            raise ValueError("EARBUD_MAC_ADDRESS environment variable is not set. Please check your .env file.")
        print("Mac", self.TARGET_MAC)
        self.TARGET_PORT = 15
        self.bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self.operation_id = 0
        self.connected = False
        self.connecting = False
        self.terminate = False
        self.readerThread = threading.Thread(target=self.reader)
        self.readerThread.start()
        self.pingerThread = threading.Thread(target=self.pinger)
        self.pingerThread.start()
        self.connectorThread = threading.Thread(target=self.auto_connect)
        self.connectorThread.start()
        self.batteryStatus = { "left": "DISCONNECTED", "right": "DISCONNECTED", "case": "DISCONNECTED" }
        self.overlay = overlay
        self.first_animation_loaded = False
        self.first_in_ear = False
        self.pinging_eel = False

    def crc16(self, buffer):
        """Calculate CRC16 for the command packet"""
        crc = 0xFFFF
        for byte in buffer:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc
    

    def auto_connect(self):
        """Connect to the earbuds"""
        if self.connecting or self.connected or self.terminate:
            return
        print("Connecting to earbuds...")
        self.connecting = True
        while not self.terminate:
            try:
                threading.Thread(target=self.eelPing).start()
                self.bt_socket.connect((self.TARGET_MAC, self.TARGET_PORT))
                self.on_connect()
                break
            except OSError as e:
                print(f"Connection failed. Retrying... {e}")
                if "already connected socket" in str(e):
                    try:
                        self.bt_socket.close()
                    except OSError:
                        pass
                    self.bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

                time.sleep(2.5)
                self.connected = False
        self.connecting = False


    def on_disconnect(self):
        """Handle disconnection"""
        print("Disconnected from earbuds. Reconnecting...")
        self.connected = False
        self.batteryStatus = { "left": "DISCONNECTED", "right": "DISCONNECTED", "case": "DISCONNECTED" }
        self.overlay.set_battery_level(self.batteryStatus)
        try:
            eel.setBattery(self.batteryStatus)
        except Exception as e:
            print(f"Error sending battery status to Eel: {e}")
        self.first_animation_loaded = False
        try:
            self.bt_socket.close()
        except OSError:
            pass
        self.bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        threading.Thread(target=self.auto_connect).start()

    def on_connect(self):
        """Handle connection"""
        print("Connected to earbuds")
        threading.Thread(target=self.eelPing).start()
        self.connected = True
        self.get_battery()
        threading.Timer(1, self.getANC).start()
        threading.Timer(2.2, self.getEQ).start()
        threading.Timer(3.4, self.getCustomEQ).start()

    def parseANC(self, hexString):
        print("Parsing ANC status...")
        hexArray = [int(hexString[i:i+2], 16) for i in range(0, len(hexString), 2)]
        ancStatus = hexArray[9]
        value = 0

        if ancStatus == 5:
            value = 2
        elif ancStatus == 7:
            value = 1
        else:
            value = 0

        print("ANC status:", ancStatus, value)
        try:
            eel.updateANC(value)
        except Exception as e:
            print(f"Error sending ANC status to Eel: {e}")

            

    def getANC(self):
        self.send(49182, [])


    def setANC(self, value):
        """
        Set ANC value.
        Args:
            value: 0 for ANC high
                   1 for Transparency
                   2 for ANC off


            sending info:
                1 - transparency
                2 - ANC off
                4 - ANC high

        """

        byteArray = [0x01, 0x01, 0x00]
        if value == 0:
            byteArray[1] = 0x01
        elif value == 1:
            byteArray[1] = 0x07
        elif value == 2:
            byteArray[1] = 0x05
        else:
            print("Invalid ANC value")
            return

        self.send(61455, byteArray)

    def setEQ(self, level):
        """
        0 - Balanced
        3 - More Bass
        2 - More Treble
        1 - Voice
        5 - Custom
        """
        byteArray = [0x00, 0x00]
        byteArray[0] = level
        self.send(61456, byteArray)
        if(level == 5):
            self.getCustomEQ()

    def getEQ(self):
        self.send(49183, [])

    def getCustomEQ(self):
        self.send(49220, [])

    def readCustomEQ(self, hexString):
        print("readCustomEQ called")
        level = []
        for i in range(3):
            array = []
            for j in range(4):
                array.append(hexString[14 + (i * 13) + j])
            level.append(self.fromFormatFloatForEQ(array))
        
        formatedArray = [int(level[2]), int(level[0]), int(level[1])]
        print(formatedArray)
        try:
            eel.setCustomEQ(formatedArray)
        except Exception as e:
            print(f"Error sending custom EQ to Eel: {e}")

    def setCustomEQ_BT(self, level):
        byteArray = [
            0x03, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x75, 0x44, 0xc3, 0xf5,
            0x28, 0x3f, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0xc0, 0x5a, 0x45, 0x00, 0x00, 0x80, 0x3f, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0c, 0x43, 0xcd, 0xcc, 0x4c, 0x3f, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00
        ]

        # Find the highest value in the level array
        highestValue = max(level)
        highestValue /= -1

        # Format and set the highest value in the byte array
        array = self.formatFloatForEQ(highestValue, True)
        for j in range(4):
            byteArray[1 + j] = array[j]

        # Format and set each level in the byte array
        for i in range(3):
            array = self.formatFloatForEQ(level[i], False)
            for j in range(4):
                byteArray[6 + (i * 13) + j] = array[j]

        # Send the byte array with the custom command
        self.send(61505, byteArray)

        threading.Timer(1, self.getCustomEQ).start()


    def formatFloatForEQ(self, f, total):
        # Create a 4-byte array for the float
        buffer = np.zeros(4, dtype=np.uint8)
        view = np.array([f], dtype='>f4').view(np.uint8)
        
        # Copy the big-endian float bytes into the buffer
        buffer[:] = view

        # Check for the special case where the float is not zero and the first three bytes are zero
        if f != 0.0 and buffer[0] == 0 and buffer[1] == 0 and buffer[2] == 0:
            buffer[3] = (buffer[3] | 0x80) & 0xFF

        # Reverse the array in place
        buffer = buffer[::-1]

        # Apply total condition
        if total:
            if f >= 0:
                buffer = np.array([0x00, 0x00, 0x00, 0x80], dtype=np.uint8)

        return buffer

    def fromFormatFloatForEQ(self, array):
        # Reverse the array
        for i in range(len(array) // 2):
            j = len(array) - i - 1
            array[i], array[j] = array[j], array[i]

        if array[0] == 0 and array[1] == 0 and array[2] == 0 and (array[3] & 0x80):
            array[3] &= 0x7F
            buffer = np.array(array, dtype=np.uint8).tobytes()
            f = np.frombuffer(buffer, dtype='>f4')[0]
            return -f
        else:
            buffer = np.array(array, dtype=np.uint8).tobytes()
            f = np.frombuffer(buffer, dtype='>f4')[0]
            return f



    def readEQ(self, hexString):
        print("readEQ called")
        hexArray = [int(hexString[i:i+2], 16) for i in range(0, len(hexString), 2)]
        eqMode = hexArray[8]
        print("eqMode ", eqMode)
        eel.setEQfromRead(eqMode)
        #setEQfromRead(eqMode)

    def pinger(self):
        """Send ping command to the earbuds to keep the connection alive"""
        while not self.terminate:
            if self.connected:
                try:
                    self.get_battery()
                    threading.Thread(target=self.eelPing).start()
                except OSError:
                    self.on_disconnect()
            time.sleep(60)

    def eelPing(self):
        if self.pinging_eel:
            return
        time.sleep(1)
        self.pinging_eel = True
        MAX_RETRIES = 2
        TIMEOUT = 2  # seconds
        
        for attempt in range(MAX_RETRIES):
            try:
                print(f"Sending ping to Eel (attempt {attempt + 1}/{MAX_RETRIES})")
                
                # Create event for timeout handling
                done = threading.Event()
                result = [None]
                
                def ping_with_timeout():
                    try:
                        result[0] = eel.ping()()
                        done.set()
                    except Exception:
                        done.set()
                
                # Start ping in thread
                threading.Thread(target=ping_with_timeout).start()
                
                # Wait with timeout
                if done.wait(timeout=TIMEOUT):
                    if result[0] == "pong":
                        print("Ping successful")
                        self.pinging_eel = False
                        return True
                
                print("Ping timed out or failed, restarting Eel...")
                threading.Thread(target=start_eel).start()
                time.sleep(2)  # Wait for restart
                
            except Exception as e:
                print(f"Error during ping attempt {attempt + 1}: {e}")
        self.pinging_eel = False
        return False
    def reader(self):
        
        while not self.terminate:
            if not self.connected:
                time.sleep(1)
                continue
            try:
                data = self.bt_socket.recv(1024)
            except OSError:
                self.on_disconnect()
                continue

            print(f"\nReceived notification data: {data.hex()}")
            if len(data) < 10 or data[0] != 0x55:
                print("Invalid notification format. Assuming disconnection...")
                self.on_disconnect()
                continue
                
            command = (data[4] << 8) | data[3]
            print(f"Notification command: {hex(command)}")
            hexString = "".join([f'{byte:02x}' for byte in data])
            if command in [16391, 57345]:
                self.readBattery(hexString)
                self.first_in_ear = True
            elif not self.first_in_ear:
                self.first_in_ear = True
                self.get_battery()


            if command in [57347, 16414]:
                self.parseANC(hexString)


            if command == 16452:
                self.readCustomEQ(data)


            if command in [16415, 16464]:
                self.readEQ(hexString)
            
        
    def get_battery(self):
        """Get battery status of the earbuds"""
        self.send(49159, [])

    def send(self, command, payload=None):
        """Send command to the buds with header, CRC, and optional operation tracking"""
        if payload is None:
            payload = []

        # Create header
        header = [0x55, 0x60, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]

        # Increment operation ID
        self.operation_id = (self.operation_id % 250) + 1
        header[7] = self.operation_id

        # Set command bytes (command is a 16-bit value)
        command_bytes = np.frombuffer(np.array([command], dtype=np.uint16).tobytes(), dtype=np.uint8)
        header[3] = int(command_bytes[0])
        #header[4] = (~int(command_bytes[1])+ 1) & 0xFF
        header[4] = int(command_bytes[1])

        # Set payload length
        header[5] = len(payload)

        # Combine header and payload
        byte_array = bytearray(header)
        byte_array.extend(payload)

        # Calculate CRC
        crc = self.crc16(byte_array)
        byte_array.extend([crc & 0xFF, (crc >> 8) & 0xFF])


        # Convert to hex for logging
        print(f"Sending: {' '.join([f'{byte:02x}' for byte in byte_array])}")
        try:
            self.bt_socket.send(bytes(byte_array))
        except OSError:
            print("Failed to send command")
            self.on_disconnect()
        
    def readBattery(self, hexString):
        print("Reading battery status...")
        connectedDevices = 0
        deviceIdToKey = { 0x02: "left", 0x03: "right", 0x04: "case" }
        BATTERY_MASK = 127
        RECHARGING_MASK = 128
        hexArray = [int(hexString[i:i+2], 16) for i in range(0, len(hexString), 2)]

        connectedDevices = hexArray[8]
        for i in range(connectedDevices):
            deviceId = hexArray[9 + (i * 2)]
            key = deviceIdToKey.get(deviceId, "DISCONNECTED")
            battery_level = hexArray[10 + (i * 2)] & BATTERY_MASK
            is_charging = (hexArray[10 + (i * 2)] & RECHARGING_MASK) == RECHARGING_MASK
            self.batteryStatus[key] = {
                "batteryLevel": battery_level,
                "isCharging": is_charging
            }

        self.overlay.set_battery_level(self.batteryStatus)
        try:
            eel.setBattery(self.batteryStatus)
        except Exception as e:
            print(f"Error sending battery status to Eel: {e}")

        if not self.first_animation_loaded:
            self.first_animation_loaded = True
            showOverlay = threading.Thread(target=self.overlay.animate_connection)
            showOverlay.start()


class CustomLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rotation = 0
        self._scale = 1.0
        self._original_pixmap = None
        self._text = ""
        self._h_offset = 0
        self._text_color = QColor(0, 0, 0)  # Default black
        self._font = QFont()  # Default font
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(1, 1)
    
    @pyqtProperty(float)
    def rotation(self):
        return self._rotation
    
    @rotation.setter
    def rotation(self, angle):
        self._rotation = angle
        self.updateGeometry()
        self.update()
    
    @pyqtProperty(float)
    def scale(self):
        return self._scale
    
    @scale.setter
    def scale(self, value):
        self._scale = value
        self.updateGeometry()
        self.update()


    @pyqtProperty(float)
    def horizontalOffset(self):
        return self._h_offset
    
    @horizontalOffset.setter
    def horizontalOffset(self, value):
        self._h_offset = value
        self.update()
    
    def setHorizontalOffset(self, offset):
        """Set horizontal offset in pixels"""
        self._h_offset = offset
        self.update()
    
    def setPixmap(self, pixmap):
        self._original_pixmap = pixmap
        self.updateGeometry()
        super().setPixmap(pixmap)
    
    def setText(self, text):
        self._text = text
        self.update()
    
    def setTextColor(self, color, alpha=255):
        """
        Set text color with transparency
        Args:
            color: QColor or string like 'red' or '#FF0000'
            alpha: 0-255 transparency value (0=transparent, 255=opaque)
        """
        if isinstance(color, str):
            if color.startswith('#') and len(color) == 8:  # Has alpha channel #AARRGGBB
                self._text_color = QColor(color)
            else:
                self._text_color = QColor(color)
                self._text_color.setAlpha(alpha)
        else:
            self._text_color = color
            self._text_color.setAlpha(alpha)
        self.update()
    
    def setTextFont(self, font_name=None, size=None, weight=None, italic=False):
        """Set text font properties"""
        if font_name:
            self._font.setFamily(font_name)
        if size:
            self._font.setPointSize(size)
        if weight:
            self._font.setWeight(weight)
        self._font.setItalic(italic)
        self.update()
    
    def setBold(self, bold=True):
        """Convenience method to set/unset bold text"""
        self._font.setBold(bold)
        self.update()
    
    def sizeHint(self):
        if not self._original_pixmap and not self._text:
            return super().sizeHint()
            
        # Calculate base size including both pixmap and text
        fm = QFontMetrics(self._font)
        text_height = fm.height() if self._text else 0
        text_width = fm.horizontalAdvance(self._text) if self._text else 0
        
        if self._original_pixmap:
            pixmap_width = self._original_pixmap.width()
            pixmap_height = self._original_pixmap.height()
        else:
            pixmap_width = 0
            pixmap_height = 0
            
        # Total height including spacing
        total_width = max(pixmap_width, text_width)
        total_height = pixmap_height + (text_height + 10 if self._text else 0)
        
        # Account for rotation and scaling
        w = total_width * self._scale
        h = total_height * self._scale
        diagonal = (w**2 + h**2)**0.5
        
        return QSize(int(diagonal), int(diagonal))
    
    def paintEvent(self, event):
        if not self._original_pixmap and not self._text:
            return super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.HighQualityAntialiasing |
            QPainter.TextAntialiasing
        )
        
        widget_rect = self.rect()
        center_x = widget_rect.width() / 2
        center_y = widget_rect.height() / 2
        
        # Save state and set up transformations
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self._rotation)
        painter.scale(self._scale, self._scale)
        
        # Set font and color for text
        painter.setFont(self._font)
        painter.setPen(self._text_color)
        
        # Calculate vertical layout
        total_height = 0
        if self._original_pixmap:
            total_height += self._original_pixmap.height()
        if self._text:
            fm = painter.fontMetrics()
            total_height += fm.height() + 10  # Add spacing between image and text
            
        # Current Y position to start drawing
        current_y = -total_height / 2
        
        # Draw pixmap if exists
        if self._original_pixmap:
            pixmap_width = self._original_pixmap.width()
            pixmap_height = self._original_pixmap.height()
            x = -pixmap_width / 2
            
            target_rect = QRect(
                int(x),
                int(current_y),
                pixmap_width,
                pixmap_height
            )
            painter.drawPixmap(target_rect, self._original_pixmap)
            current_y += pixmap_height + 10  # Add spacing after pixmap
        
        # Draw text if exists
        if self._text:
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(self._text)
            text_x = -text_width / 2
            
            painter.drawText(
                int(text_x) + int(self._h_offset),
                int(current_y + fm.ascent()),
                self._text
            )
        
        painter.restore()


class TransparentOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set proper window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Tool |  # Keeps the window on top of other app windows but below the taskbar
            Qt.SubWindow |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.win_width = 300
        self.win_height = 200
        self.setFixedSize(self.win_width, self.win_height)
        
        # Create central widget and set its background
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: red;")
        self.setCentralWidget(central_widget)
        
        # Get screen geometry
        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()
        self.battery_status = { "left": "DISCONNECTED", "right": "DISCONNECTED", "case": "DISCONNECTED" }
        
        self.left_earbud_image_path = "web/ear_corsola_black_left.png"
        self.right_earbud_image_path = "web/ear_corsola_black_right.png"
        self.signal_emitter = SignalEmitter()
        self.signal_emitter.show_overlay.connect(self.show_animation)
        self.init_ui()


    def set_battery_level(self, battery_status):
        # Update battery levels for each earbud
        for key, value in battery_status.items():
            if key in self.battery_status:
                self.battery_status[key] = value
        print("Battery status updated:", self.battery_status)

        leftText = ""
        rightText = ""
        if self.battery_status["left"] != "DISCONNECTED":
            leftText = f"{self.battery_status['left'].get('batteryLevel',0)}%"
            self.left_label.setVisible(True)
        else:
            # hide the label
            self.left_label.setVisible(False)
        if self.battery_status["right"] != "DISCONNECTED":
            rightText = f"{self.battery_status['right'].get('batteryLevel',0)}%"
            self.right_label.setVisible(True)
        else:
            # hide the label
            self.right_label.setVisible(False)


        # Update text labels
        self.left_label.setText(leftText)
        self.right_label.setText(rightText)


    def raise_to_top(self):
        self.show()  # Ensure visibility
        self.raise_()  # Bring to front
        self.activateWindow()  # Activate to maintain focus


        
    def init_ui(self):
        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Horizontal layout for earbuds
        earbud_layout = QHBoxLayout()
        earbud_layout.setAlignment(Qt.AlignCenter)  # Center horizontally
        earbud_layout.setContentsMargins(10, 10, 10, 10)
        
        # Left earbud
        self.left_label = CustomLabel()
        self.left_label.setText("100%")
        self.left_label.setTextColor("white", 200)
        self.left_label.setHorizontalOffset(8)
        left_pixmap = QPixmap(self.left_earbud_image_path)
        scaled_left = left_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.left_label.setPixmap(scaled_left)
        self.left_label.setAlignment(Qt.AlignCenter)
        self.left_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Right earbud
        self.right_label = CustomLabel()
        self.right_label.setText("100%")
        self.right_label.setTextColor("white", 200)
        self.right_label.setHorizontalOffset(-8)
        right_pixmap = QPixmap(self.right_earbud_image_path)
        scaled_right = right_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.right_label.setPixmap(scaled_right)
        self.right_label.setAlignment(Qt.AlignCenter)
        self.right_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Add to horizontal layout
        earbud_layout.addWidget(self.left_label)
        earbud_layout.addSpacing(-40)  # Increased spacing
        earbud_layout.addWidget(self.right_label)
        
        # Add to main layout and center
        main_layout.addLayout(earbud_layout)
        main_layout.setAlignment(Qt.AlignCenter)  # Center vertically

        # if any of the label are clicked, emit signal to show overlay
        self.left_label.mousePressEvent = show_eel_window
        self.right_label.mousePressEvent = show_eel_window
        
        
    def setup_animations(self):
        # Calculate positions
        start_y = self.screen_height + 300
        mid_y = self.screen_height - self.height() - 100
        end_y = self.screen_height + 300
        x_pos = self.screen_width - self.win_width - 60

        # Smooth up animation
        self.animation_up = QPropertyAnimation(self, b"pos")
        self.animation_up.setDuration(1500)
        self.animation_up.setEasingCurve(QEasingCurve.OutCubic)
        self.animation_up.setStartValue(QPoint(x_pos, start_y))
        self.animation_up.setEndValue(QPoint(x_pos, mid_y))

        # Replace the wait animation with breathing sequence
        self.breathing_group = QSequentialAnimationGroup()
        
        # Create subtle up motion
        self.breathe_up = QPropertyAnimation(self, b"pos")
        self.breathe_up.setDuration(1750)  # Half of total time
        self.breathe_up.setStartValue(QPoint(x_pos, mid_y))
        self.breathe_up.setEndValue(QPoint(x_pos, mid_y + 10))  # Move up slightly
        self.breathe_up.setEasingCurve(QEasingCurve.InOutSine)
        
        # Create subtle down motion
        self.breathe_down = QPropertyAnimation(self, b"pos")
        self.breathe_down.setDuration(1750)  # Half of total time
        self.breathe_down.setStartValue(QPoint(x_pos, mid_y + 10))
        self.breathe_down.setEndValue(QPoint(x_pos, mid_y))
        self.breathe_down.setEasingCurve(QEasingCurve.InOutSine)
        
        # Add to sequence
        self.breathing_group.addAnimation(self.breathe_up)
        self.breathing_group.addAnimation(self.breathe_down)
        
        # Replace original wait animation
        self.animation_wait = self.breathing_group


        # Quick fade out
        self.animation_down = QPropertyAnimation(self, b"pos")
        self.animation_down.setDuration(1000)
        self.animation_down.setEasingCurve(QEasingCurve.InCubic)
        self.animation_down.setStartValue(QPoint(x_pos, mid_y))
        self.animation_down.setEndValue(QPoint(x_pos, end_y))

        # Sequential group
        self.animation_group = QSequentialAnimationGroup()
        self.animation_group.addAnimation(self.animation_up)
        self.animation_group.addAnimation(self.animation_wait)
        self.animation_group.addAnimation(self.animation_down)

    def setup_buds_animations(self):
        """Create enhanced animations for earbuds"""
        self.max_scale = 1.1
        # Create rotation animations for each bud
        self.left_rotation = QPropertyAnimation(self.left_label, b"rotation")
        self.right_rotation = QPropertyAnimation(self.right_label, b"rotation")
        
        # Create scale animations for each bud
        self.left_scale_up = QPropertyAnimation(self.left_label, b"scale")
        self.right_scale_up = QPropertyAnimation(self.right_label, b"scale")

        # Configure rotation animations
        self.left_rotation.setDuration(1200)
        self.left_rotation.setStartValue(20)
        self.left_rotation.setEndValue(-20)
        self.left_rotation.setEasingCurve(QEasingCurve.InOutBack)

        self.right_rotation.setDuration(1200)
        self.right_rotation.setStartValue(-20)
        self.right_rotation.setEndValue(20)
        self.right_rotation.setEasingCurve(QEasingCurve.InOutBack)

        # Configure scale animations (up and down for a pulse effect)
        self.left_scale_up.setDuration(1200)
        self.left_scale_up.setStartValue(0.4)
        self.left_scale_up.setEndValue(self.max_scale)
        self.left_scale_up.setEasingCurve(QEasingCurve.InOutBack)

        self.right_scale_up.setDuration(1200)
        self.right_scale_up.setStartValue(0.4)
        self.right_scale_up.setEndValue(self.max_scale)
        self.right_scale_up.setEasingCurve(QEasingCurve.InOutBack)

        self.wait_animation = QPropertyAnimation(self.right_label, b"scale")  # opacity is dummy property
        self.wait_animation.setDuration(3500)  # 1 second wait
        self.wait_animation.setStartValue(self.max_scale)
        self.wait_animation.setEndValue(self.max_scale)


        # Create additional animations for buds going down
        self.left_rotation_back = QPropertyAnimation(self.left_label, b"rotation")
        self.right_rotation_back = QPropertyAnimation(self.right_label, b"rotation")

        self.left_rotation_back.setDuration(1000)
        self.left_rotation_back.setStartValue(-20)
        self.left_rotation_back.setEndValue(0)
        self.left_rotation_back.setEasingCurve(QEasingCurve.InQuint)

        self.right_rotation_back.setDuration(1000)
        self.right_rotation_back.setStartValue(20)
        self.right_rotation_back.setEndValue(0)
        self.right_rotation_back.setEasingCurve(QEasingCurve.InQuint)

        self.left_scale_reset = QPropertyAnimation(self.left_label, b"scale")
        self.right_scale_reset = QPropertyAnimation(self.right_label, b"scale")

        self.left_scale_reset.setDuration(1000)
        self.left_scale_reset.setStartValue(self.max_scale)
        self.left_scale_reset.setEndValue(0.3)
        self.left_scale_reset.setEasingCurve(QEasingCurve.InQuint)

        self.right_scale_reset.setDuration(1000)
        self.right_scale_reset.setStartValue(self.max_scale)
        self.right_scale_reset.setEndValue(0.3)
        self.right_scale_reset.setEasingCurve(QEasingCurve.InQuint)

        # Group animations in a parallel group for smooth simultaneous effects
        self.buds_group = QParallelAnimationGroup()
        self.buds_group.addAnimation(self.left_rotation)
        self.buds_group.addAnimation(self.right_rotation)
        self.buds_group.addAnimation(self.left_scale_up)
        self.buds_group.addAnimation(self.right_scale_up)
        

        # Add animations for buds going back down
        self.buds_down_group = QParallelAnimationGroup()
        self.buds_down_group.addAnimation(self.left_rotation_back)
        self.buds_down_group.addAnimation(self.right_rotation_back)
        self.buds_down_group.addAnimation(self.left_scale_reset)
        self.buds_down_group.addAnimation(self.right_scale_reset)

        # Sequential group for looping the scale up, scale down, and going down
        self.buds_animation_group = QSequentialAnimationGroup()
        self.buds_animation_group.addAnimation(self.buds_group)
        self.buds_animation_group.addAnimation(self.wait_animation)
        self.buds_animation_group.addAnimation(self.buds_down_group)


    def show_animation(self):
        self.move(self.screen_width - self.win_width, self.screen_height - 100)
        #super().show()
        self.raise_to_top()
        self.setup_animations()
        self.setup_buds_animations()
        # Start both animation groups
        self.animation_group.start()
        self.buds_animation_group.start()
        print("rotating animation started")

    def animate_connection(self):
        """Emit signal instead of direct show"""
        print("Emitting signal to show overlay")
        self.signal_emitter.show_overlay.emit()


def start_eel():
    try:
        print("Starting Eel")
        eel.init("web")
        eel.browsers.set_path('electron', r'.\electron-v31.0.0-alpha.2-win32-x64\electron.exe')
        threading.Thread(target = lambda :eel.start("main.html", mode="electron")).start()
    except Exception as e:
        print(f"Error starting Eel: {e}")

def show_eel_window(_=None):
    print("Showing Eel window")
    try:
        eel.toggleVisibility()
        print("Command sent")
    except Exception as e:
        print(f"Error showing window: {e}")

def main():
    app = QApplication(sys.argv)
    threading.Thread(target=start_eel).start()
    
    overlay = TransparentOverlay()
    glassX = EarX(overlay)

    eel.expose(glassX.setANC)
    eel.expose(glassX.setEQ)
    eel.expose(glassX.setCustomEQ_BT)

    
    # Set up clean exit handler
    def cleanup():
        print("Shutting down...")
        # First stop the main loop and disconnect
        glassX.connected = False
        glassX.terminate = True
        
        try:
            glassX.bt_socket.close()
            print("Socket closed")
        except:
            pass

        try:
            eel.exitApp()
            print("Eel exited")
        except:
            pass

        # Remove tray icon before quitting
        tray.hide()
        
        # Stop Qt event loop
        app.quit()
        print("App quit")

        # Small delay to let Qt cleanup
        time.sleep(0.5)
        
        # Force stop remaining threads
        for thread in threading.enumerate():
            if thread != threading.main_thread():
                try:
                    thread._stop()
                except:
                    pass
        print("All threads stopped")

        # Use only one exit call
        os._exit(0)
        
    
    # Handle system signals
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
        # Create system tray icon
    tray = QSystemTrayIcon()
    icon = QIcon("web/cmf.png")
    tray.setIcon(icon)
    tray.setVisible(True)
    
    # Create menu with Show and Exit options
    menu = QMenu()
    menu.setWindowFlags(menu.windowFlags() | Qt.Popup)


    show_action = menu.addAction("Show")
    show_action.triggered.connect(show_eel_window)
    
    menu.addSeparator()  # Add a separator line between actions
    quit_action = menu.addAction("Exit")
    quit_action.triggered.connect(cleanup)

    def hideMenuOnClick():
        menu.hide()

    menu.aboutToHide.connect(hideMenuOnClick)


    tray.setContextMenu(menu)

    
    # Keep the existing click behavior
    tray.activated.connect(lambda reason: show_eel_window() if reason == QSystemTrayIcon.Trigger else None)
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        cleanup()
            
if __name__ == '__main__':
    main()