# 🚀 How to Use (Screenshot to Text Extractor – Python)

This project is a Lens-like Screenshot to Text Extractor built with Python, PyQt5, and Tesseract OCR. It allows you to paint over any area on the screen and automatically extract text to the clipboard.

## 🧰 Requirements

Windows OS

Python 3.8+

Tesseract OCR (installed on system)

## 🔧 Installation Steps
1️⃣ Clone the Repository
```javascript
git clone https://github.com/USERNAME/REPOSITORY_NAME.git
cd REPOSITORY_NAME
```

2️⃣ Create Virtual Environment (Optional but Recommended)
```javascript
python -m venv venv
```


Activate it:

Windows

```javascript
venv\Scripts\activate
```

3️⃣ Install Required Python Packages
```javascript
pip install PyQt5 pillow pytesseract numpy
```

4️⃣ Install Tesseract OCR

Download and install Tesseract OCR for Windows:

https://github.com/UB-Mannheim/tesseract/wiki

## ⚠️ After installation, verify the path in the Python file:

```javascript
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```


Update this path if Tesseract is installed elsewhere.

▶️ Run the Application
```javascript
python screenshot_to_text_extractor_final.py
```


(Use your actual file name if different)

## 🖱️ How It Works

A floating bubble icon appears on the screen

Click the bubble → Start Select (paint)

The screen freezes and enters paint mode

Left mouse drag → paint/select text area

Right mouse drag → erase selection

Press Enter or click Done

OCR runs in the background

Extracted text is automatically copied to clipboard

Optional: Open OCR Window to view or save the text

## ✨ Features

Full-screen screenshot capture

Paint-based text selection

Background OCR processing

Automatic clipboard copy

Handles:

Exponents (10⁶ → 10^6)

Scientific notation

Square roots & nth roots

Floating, draggable UI

Supports multiple languages (eng + hin)

## 🌐 Change OCR Language (Optional)

Inside the file:

```javascript
OCR_LANG = "eng+hin"
```


Examples:

```javascript
OCR_LANG = "eng"
OCR_LANG = "eng+fra"
```

## 🛑 Exit Application

Close from Task Manager

Or stop the Python process in terminal (Ctrl + C)
