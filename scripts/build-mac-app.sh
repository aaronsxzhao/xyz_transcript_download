#!/bin/bash
#
# Build script for XYZ Podcast Mac App Bundle
# Creates a .app bundle that can be distributed to users
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="XYZ Podcast"
BUNDLE_ID="com.xyz.podcast-transcript"
VERSION="1.0.0"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/build"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Building ${APP_NAME} Mac App${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Clean previous build
echo -e "${BLUE}Cleaning previous build...${NC}"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# Build React frontend
echo -e "${BLUE}Building React frontend...${NC}"
if [[ -d "${PROJECT_DIR}/web/node_modules" ]]; then
    cd "${PROJECT_DIR}/web"
    npm run build
    echo -e "${GREEN}✓ Frontend built successfully${NC}"
else
    echo -e "${YELLOW}Warning: node_modules not found. Skipping frontend build.${NC}"
    echo -e "${YELLOW}Run 'cd web && npm install && npm run build' first.${NC}"
fi

# Create app bundle structure
echo -e "${BLUE}Creating app bundle structure...${NC}"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources/app"

# Create Info.plist
echo -e "${BLUE}Creating Info.plist...${NC}"
cat > "${APP_BUNDLE}/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2024. MIT License.</string>
</dict>
</plist>
EOF

# Create launcher script
echo -e "${BLUE}Creating launcher script...${NC}"
cat > "${APP_BUNDLE}/Contents/MacOS/launcher" << 'LAUNCHER_EOF'
#!/bin/bash
#
# XYZ Podcast App Launcher
#

# Get the Resources directory
RESOURCES_DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
APP_DIR="${RESOURCES_DIR}/app"

# Source and run the main launch script
exec "${APP_DIR}/scripts/launch.sh"
LAUNCHER_EOF

chmod +x "${APP_BUNDLE}/Contents/MacOS/launcher"

# Copy project files
echo -e "${BLUE}Copying project files...${NC}"

# Copy Python files
cp "${PROJECT_DIR}"/*.py "${APP_BUNDLE}/Contents/Resources/app/" 2>/dev/null || true
cp "${PROJECT_DIR}/requirements.txt" "${APP_BUNDLE}/Contents/Resources/app/"

# Copy API directory
cp -r "${PROJECT_DIR}/api" "${APP_BUNDLE}/Contents/Resources/app/"

# Copy scripts directory
cp -r "${PROJECT_DIR}/scripts" "${APP_BUNDLE}/Contents/Resources/app/"

# Copy web directory (only dist if available, otherwise full)
if [[ -d "${PROJECT_DIR}/web/dist" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/app/web"
    cp -r "${PROJECT_DIR}/web/dist" "${APP_BUNDLE}/Contents/Resources/app/web/"
    echo -e "${GREEN}✓ Pre-built frontend included${NC}"
else
    echo -e "${YELLOW}⚠ No pre-built frontend found${NC}"
fi

# Copy .env.example as reference
if [[ -f "${PROJECT_DIR}/.env.example" ]]; then
    cp "${PROJECT_DIR}/.env.example" "${APP_BUNDLE}/Contents/Resources/app/"
fi

# Copy icon if exists
if [[ -f "${PROJECT_DIR}/scripts/icon.icns" ]]; then
    cp "${PROJECT_DIR}/scripts/icon.icns" "${APP_BUNDLE}/Contents/Resources/icon.icns"
    echo -e "${GREEN}✓ App icon included${NC}"
else
    echo -e "${YELLOW}⚠ No icon.icns found, using default${NC}"
fi

# Create a simple README for the app
cat > "${APP_BUNDLE}/Contents/Resources/README.txt" << 'README_EOF'
XYZ Podcast Transcript & Summary Tool
======================================

Requirements:
- macOS 10.15 or later
- Python 3.9 or higher
- FFmpeg (for audio processing)

First Run:
- Double-click the app to start
- Dependencies will be automatically installed
- Your browser will open to the web interface

Data Location:
- All data is stored in ~/.xyz-podcast/

Need Help?
- Check the README.md in the app bundle for detailed instructions
README_EOF

# Calculate size
APP_SIZE=$(du -sh "${APP_BUNDLE}" | cut -f1)
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  App: ${BLUE}${APP_BUNDLE}${NC}"
echo -e "  Size: ${APP_SIZE}"
echo ""

# Optional: Create DMG
if [[ "$1" == "--dmg" ]]; then
    echo -e "${BLUE}Creating DMG...${NC}"
    DMG_NAME="${APP_NAME}-${VERSION}.dmg"
    DMG_PATH="${BUILD_DIR}/${DMG_NAME}"
    
    # Create temporary DMG directory
    DMG_TEMP="${BUILD_DIR}/dmg_temp"
    mkdir -p "${DMG_TEMP}"
    cp -r "${APP_BUNDLE}" "${DMG_TEMP}/"
    
    # Create symlink to Applications
    ln -s /Applications "${DMG_TEMP}/Applications"
    
    # Create DMG
    hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_TEMP}" -ov -format UDZO "${DMG_PATH}"
    
    # Cleanup
    rm -rf "${DMG_TEMP}"
    
    echo -e "${GREEN}✓ DMG created: ${DMG_PATH}${NC}"
fi

# Create ZIP for easy distribution
echo -e "${BLUE}Creating ZIP archive...${NC}"
cd "${BUILD_DIR}"
zip -r -q "${APP_NAME}-${VERSION}.zip" "${APP_NAME}.app"
ZIP_SIZE=$(du -sh "${APP_NAME}-${VERSION}.zip" | cut -f1)
echo -e "${GREEN}✓ ZIP created: ${BUILD_DIR}/${APP_NAME}-${VERSION}.zip (${ZIP_SIZE})${NC}"

echo ""
echo -e "${GREEN}Distribution files ready in: ${BUILD_DIR}${NC}"
echo ""
echo "To install:"
echo "  1. Unzip '${APP_NAME}-${VERSION}.zip'"
echo "  2. Drag '${APP_NAME}.app' to Applications folder"
echo "  3. Double-click to run"
echo ""
