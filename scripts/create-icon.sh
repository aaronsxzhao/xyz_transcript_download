#!/bin/bash
#
# Create a simple app icon for XYZ Podcast
# Uses macOS sips and iconutil to create .icns file
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_DIR="${SCRIPT_DIR}/icon.iconset"

echo "Creating app icon..."

# Create iconset directory
mkdir -p "${ICON_DIR}"

# Create a simple icon using Python and PIL (if available) or use a placeholder
python3 << 'PYTHON_EOF'
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("PIL not installed, creating placeholder icon")
    sys.exit(1)

# Icon sizes needed for macOS
sizes = [16, 32, 64, 128, 256, 512, 1024]

script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.'
icon_dir = os.environ.get('ICON_DIR', './icon.iconset')

for size in sizes:
    # Create image with gradient background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    padding = size // 8
    radius = size // 5
    
    # Purple gradient-like solid color
    bg_color = (138, 43, 226, 255)  # Purple
    
    # Draw background
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=radius,
        fill=bg_color
    )
    
    # Draw microphone icon (simplified)
    center_x = size // 2
    center_y = size // 2
    mic_width = size // 5
    mic_height = size // 3
    
    # Microphone body
    mic_color = (255, 255, 255, 255)
    draw.rounded_rectangle(
        [center_x - mic_width//2, center_y - mic_height//2,
         center_x + mic_width//2, center_y + mic_height//4],
        radius=mic_width//2,
        fill=mic_color
    )
    
    # Microphone stand
    stand_width = size // 20
    draw.rectangle(
        [center_x - stand_width//2, center_y + mic_height//4,
         center_x + stand_width//2, center_y + mic_height//2 + size//10],
        fill=mic_color
    )
    
    # Base
    base_width = size // 4
    draw.rectangle(
        [center_x - base_width//2, center_y + mic_height//2 + size//12,
         center_x + base_width//2, center_y + mic_height//2 + size//8],
        fill=mic_color
    )
    
    # Save at different sizes
    img.save(os.path.join(icon_dir, f'icon_{size}x{size}.png'))
    if size <= 512:
        img_2x = img.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
        img_2x.save(os.path.join(icon_dir, f'icon_{size}x{size}@2x.png'))

print("Icon images created successfully!")
PYTHON_EOF

PYTHON_EXIT=$?

if [[ $PYTHON_EXIT -ne 0 ]]; then
    echo "Creating simple placeholder icons..."
    
    # Create placeholder PNGs using sips (built into macOS)
    # First, create a simple colored square PNG
    
    # Use built-in macOS tools to create a simple icon
    # Create a temporary HTML file and render it
    
    # Fallback: Create minimal valid PNG files
    for size in 16 32 128 256 512; do
        # Create a minimal purple PNG using base64
        # This is a 1x1 purple pixel that we'll resize
        python3 -c "
import struct
import zlib

def create_png(width, height, color):
    def make_chunk(chunk_type, data):
        chunk_len = struct.pack('>I', len(data))
        chunk_crc = struct.pack('>I', zlib.crc32(chunk_type + data) & 0xffffffff)
        return chunk_len + chunk_type + data + chunk_crc
    
    # PNG signature
    signature = b'\\x89PNG\\r\\n\\x1a\\n'
    
    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr = make_chunk(b'IHDR', ihdr_data)
    
    # IDAT chunk (image data)
    raw_data = b''
    for y in range(height):
        raw_data += b'\\x00'  # Filter byte
        for x in range(width):
            raw_data += bytes(color)  # RGBA
    
    compressed = zlib.compress(raw_data)
    idat = make_chunk(b'IDAT', compressed)
    
    # IEND chunk
    iend = make_chunk(b'IEND', b'')
    
    return signature + ihdr + idat + iend

# Purple color
color = (138, 43, 226, 255)
png_data = create_png($size, $size, color)

with open('${ICON_DIR}/icon_${size}x${size}.png', 'wb') as f:
    f.write(png_data)
"
    done
    
    echo "Placeholder icons created"
fi

# Rename files to match Apple's expected naming
cd "${ICON_DIR}"
for f in icon_*.png; do
    # Convert icon_16x16.png to icon_16x16.png format expected by iconutil
    newname=$(echo "$f" | sed 's/icon_/icon_/')
    if [[ "$f" != "$newname" ]]; then
        mv "$f" "$newname" 2>/dev/null || true
    fi
done

# Create .icns file using iconutil
cd "${SCRIPT_DIR}"
if command -v iconutil &> /dev/null; then
    iconutil -c icns "${ICON_DIR}" -o "${SCRIPT_DIR}/icon.icns"
    echo "Created icon.icns"
    rm -rf "${ICON_DIR}"
else
    echo "iconutil not found, keeping PNG files in ${ICON_DIR}"
fi

echo "Done!"
