
### Termux Setup for Telegram Bot

1. **Install Termux**
   - Download Termux from F-Droid (recommended) or Play Store
   - Open the app after installation

2. **Update packages**
   ```bash
   pkg update && pkg upgrade
   ```

3. **Install required dependencies**
   ```bash
   pkg install python git sqlite
   ```

4. **Clone the bot repository**
   ```bash
   git clone https://github.com/deepseekhandle/X-Space-T.git
   cd X-Space-T
   ```

5. **Install Python dependencies**
   ```bash
   pip install python-telegram-bot aiohttp
   ```

6. **Run the bot**
   ```bash
   python run.py
   ```

### Important Notes:

1. **Running in Background**:
   - To keep the bot running when Termux is closed:
     ```bash
     pkg install termux-services
     sv-enable your_bot_service
     ```

2. **API Limitations**:
   - Termux may have some network limitations
   - For production use, consider a VPS instead

3. **Bot Token Security**:
   - Never share your bot token
   - The token in the code should be replaced with your actual token

4. **Termux Permissions**:
   - Grant storage permission if needed:
   ```bash
   termux-setup-storage
   ```

