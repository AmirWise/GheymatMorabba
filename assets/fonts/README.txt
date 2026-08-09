This folder is empty on purpose -- I can't generate real font files
(Vazirmatn, SF Pro Display, Inter are licensed typefaces with binary
.ttf data I don't have access to and can't fabricate).

utils.py's _load_resources() looks for these exact filenames here:

    Vazirmatn-Regular.ttf
    SF-Pro-Display-Regular.ttf
    Inter-Regular.ttf

Drop your existing copies of those three files into this folder and the
app will pick them up automatically -- ResourceManager.load_font()
already checks whether the file exists before doing anything, so nothing
breaks if one is missing; it just falls back to the OS's default font
for that platform (Segoe UI on Windows, etc.), which is exactly what was
happening silently before this note existed.
