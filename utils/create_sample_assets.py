import os
import struct

os.makedirs("assets", exist_ok=True)

def create_bmp(filepath, width, height, color_rgb):
    # BMP 24-bit uncompressed
    r, g, b = color_rgb
    row_bytes = width * 3
    padding = (4 - (row_bytes % 4)) % 4
    image_size = (row_bytes + padding) * height
    file_size = 54 + image_size
    
    header = bytearray(54)
    # BM header
    header[0:2] = b'BM'
    header[2:6] = struct.pack('<I', file_size)
    header[10:14] = struct.pack('<I', 54) # offset to pixel data
    # DIB header
    header[14:18] = struct.pack('<I', 40) # header size
    header[18:22] = struct.pack('<i', width)
    header[22:26] = struct.pack('<i', height)
    header[26:28] = struct.pack('<H', 1)  # color planes
    header[28:30] = struct.pack('<H', 24) # bits per pixel
    header[34:38] = struct.pack('<I', image_size)
    
    with open(filepath, 'wb') as f:
        f.write(header)
        row = bytearray()
        for _ in range(width):
            row.extend([b, g, r]) # BMP uses BGR
        row.extend([0] * padding)
        for _ in range(height):
            f.write(row)

create_bmp('assets/sample_char1.jpg', 200, 200, (79, 70, 229))   # Indigo
create_bmp('assets/sample_prod1.jpg', 200, 200, (5, 150, 105))   # Emerald
create_bmp('assets/sample_cloth1.jpg', 200, 200, (219, 39, 119)) # Pink
print("Pure Python BMP samples written successfully")
