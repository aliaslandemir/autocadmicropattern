
# **AutoCAD MicroPattern**

---

## **Table of Contents**

- [Overview](#overview)
- [Features](#features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Setting Up the Virtual Environment](#setting-up-the-virtual-environment)
- [Usage](#usage)
  - [Running the Application](#running-the-application)
  - [Customization Options](#customization-options)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [Contact](#contact)

---

## **Overview**

**AutoCAD MicroPattern** is a Python-based application designed to generate and visualize micropatterns on hexagonal grids and transfer geometry to AutoCAD. The project features a PyQt5-based graphical user interface (GUI), integrated Matplotlib visualization, and AutoCAD interaction using `pyautocad`.

Key applications include:
- Creating hexagonal grids for micropatterning.
- Customizing grid parameters such as radius, side length, and defect orientation.
- Transferring geometry (rectangles and circles) to AutoCAD.

---

## **Features**

- **Interactive GUI:** Provides a PyQt5-based interface for easy user interaction.  
- **Hexagonal Grid Generator:** Customizable radius, side length, and nematic defect parameters.  
- **AutoCAD Integration:** Transfers grid geometry directly to AutoCAD.  
- **Real-Time Visualization:** Displays hex grids with orientation rectangles in embedded Matplotlib.  
- **Save Options:** Export visualizations as PNG or PDF.

## Screenshot

Below is a preview of the GUI:

![GUI Screenshot](docs/screenshot.png)


---

## **Getting Started**

Follow these steps to set up and run the project on your local machine.

### **Prerequisites**

Before you start, ensure the following are installed:

- **Python 3.8 or higher**
- **Git** (for cloning the repository)
- **AutoCAD** (required for transferring geometry)
- **Virtual Environment** (recommended for dependency management)

---

### **Installation**

1. **Clone the Repository**  
   ```bash
   git clone https://github.com/aliaslandemir/autocadmicropattern.git
   cd autocadmicropattern
   ```

2. **Set Up a Virtual Environment**  
   Create and activate a virtual environment to manage dependencies:
   ```bash
   python -m venv venv
   ```

   - **Windows**:  
     ```bash
     venv\Scripts\activate
     ```
   - **macOS/Linux**:  
     ```bash
     source venv/bin/activate
     ```

3. **Install Dependencies**  
   Install the required libraries using the `requirements.txt` file:
   ```bash
   pip install -r requirements.txt
   ```

---

## **Usage**

### **Running the Application**

After completing the installation steps:

1. **Activate the Virtual Environment**  
   ```bash
   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

2. **Run the Main Script**  
   Execute the main GUI application with:  
   ```bash
   python main.py
   ```

---

### **Customization Options**

You can customize grid and defect parameters directly in the GUI:
- **Hex Grid Parameters:** Set the radius and side length of the hexagonal grid.
- **Defect Orientation:** Choose 1 or 2 nematic defects and their positions.
- **Geometry:** Specify the dimensions of rectangles and circles.
- **AutoCAD Transfer:** Push the generated patterns directly to AutoCAD.

---

## **Project Structure**

```
autocadmicropattern/
├── docs/                 # Documentation and assets (e.g., screenshots, example data)
│   └── screenshot.png    # Example image or visualization output
├── GUI.py                # Main application code (contains the GUI and logic)
├── .gitignore            # Files and directories to exclude from Git
├── LICENSE               # Project license
├── README.md             # Project overview and user instructions
├── requirements.txt      # Python dependencies
└── setup.py              # For installing the package

```

---

## **Contributing**

Contributions are welcome! Please follow these steps:

1. **Fork the Repository**  
   Click the **Fork** button on GitHub to create your own copy.

2. **Clone Your Fork**  
   ```bash
   git clone https://github.com/aliaslandemir/autocadmicropattern.git
   ```

3. **Create a New Branch**  
   ```bash
   git checkout -b feature/new-feature
   ```

4. **Make Changes & Commit**  
   ```bash
   git commit -m "Add new feature"
   ```

5. **Push Changes**  
   ```bash
   git push origin feature/new-feature
   ```

6. **Submit a Pull Request**  
   Go to the original repository and create a pull request.

---

## **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## **Acknowledgments**

Special thanks to:
- The developers of `PyQt5`, `matplotlib`, and `pyautocad`.
- Contributors to open-source projects enabling AutoCAD integration.

---

## **Contact**

For questions or suggestions:

- **Name:** Ali Aslan Demir  
- **Email:** [aliaslandemir@gmail.com](mailto:aliaslandemir@gmail.com)  
- **GitHub:** [https://github.com/aliaslandemir](https://github.com/aliaslandemir)

---
