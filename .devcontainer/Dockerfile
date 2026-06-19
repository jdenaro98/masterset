FROM mcr.microsoft.com/devcontainers/javascript-node:22-bookworm

# Python and system libraries required by Electron and Playwright Chromium.
# Installing here (as root) avoids permission issues during postCreateCommand.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    xterm \
    feh \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy app icon for use as desktop wallpaper.
COPY build/icons/png/512x512.png /home/node/.fluxbox/wallpaper.png

# Open a terminal and set the wallpaper automatically when the Fluxbox desktop starts.
RUN mkdir -p /home/node/.fluxbox \
    && printf '#!/bin/bash\nfeh --bg-center /home/node/.fluxbox/wallpaper.png\nxterm -e "bash -c '\''cd /workspaces/masterset && exec bash'\''" &\nexec fluxbox\n' > /home/node/.fluxbox/startup \
    && chmod +x /home/node/.fluxbox/startup \
    && chown -R node:node /home/node/.fluxbox

# Allow pip to install packages system-wide inside the container (PEP 668 override).
ENV PIP_BREAK_SYSTEM_PACKAGES=1
