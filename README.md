# GlassControl

GlassControl is a Windows application that provides automatic connection and control for your wireless earbuds. It features:

- Automatic connection when earbuds are in range
- Battery level monitoring
- ANC (Active Noise Cancellation) control
- Equalizer settings
- System tray integration
- Elegant connection animations

## Currently Supported Devices
- CMF Buds Pro

## Requirements

- Windows 10/11
- Python 3.8
- Required Python packages:
  - PyQt5
  - bluetooth
  - numpy
  - python-dotenv
  - eel
  - psutil

## Installation

1. Clone this repository
2. Install required packages:
3. Create a .env file in the project root with your earbud's MAC address:
```
EARBUD_MAC_ADDRESS=XX:XX:XX:XX:XX:XX
```

## Task Scheduler Setup (24/7 Operation)

To run GlassControl automatically on system startup:

1. Open Task Scheduler (`taskschd.msc`)
2. Create a new Basic Task:
   - Name: "GlassControl"
   - Trigger: "At system startup"
   - Action: Start a program
   - Program/script: Path to your Python executable
   - Add arguments: Path to main.py
   - Start in: Path to project directory

(Note: After creation, go to Power settings. The task scheduler stops the application when on battery power.)

## Credits

This application uses code inspired by the [ear-web](https://github.com/radiance-project/ear-web) project. This project would not have been possible without their pioneering work in reverse engineering the earbud protocol.

## Disclaimer

This software is provided "as is" without warranty of any kind. Use at your own risk. This is not an official product and is not affiliated with CMF or Nothing Technology Limited. This software may stop working if the earbuds' firmware is updated.

## License

This project is licensed under the GNU General Public License v3.0