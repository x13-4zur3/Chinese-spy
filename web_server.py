import os
from flask import Flask, jsonify, render_template
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Discord bot reference (will be set by bot.py)
bot_instance = None

def set_bot(bot):
    """Set the bot instance so web server can access it"""
    global bot_instance
    bot_instance = bot

# ============================================
# ROUTES - URL MAPPINGS
# ============================================

@app.route('/', methods=['GET'])
def index():
    """Main dashboard page"""
    return render_template('index.html', bot_online=bot_instance is not None)

@app.route('/api/status', methods=['GET'])
def api_status():
    """Bot status API endpoint"""
    if bot_instance is None:
        return jsonify({"status": "offline", "message": "Bot not initialized"}), 503
    
    return jsonify({
        "status": "online",
        "bot_name": bot_instance.user.name if bot_instance.user else "Unknown",
        "bot_id": bot_instance.user.id if bot_instance.user else None,
        "guilds": len(bot_instance.guilds),
        "uptime": str(datetime.utcnow() - bot_instance.start_time) if hasattr(bot_instance, 'start_time') else "Unknown",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/commands', methods=['GET'])
def api_commands():
    """List all bot commands"""
    if bot_instance is None:
        return jsonify({"error": "Bot not online"}), 503
    
    commands = []
    for command in bot_instance.commands:
        commands.append({
            "name": command.name,
            "description": command.help or "No description",
            "usage": str(command)
        })
    
    return jsonify({"commands": commands, "count": len(commands)})

@app.route('/api/guilds', methods=['GET'])
def api_guilds():
    """List all guilds the bot is in"""
    if bot_instance is None:
        return jsonify({"error": "Bot not online"}), 503
    
    guilds = [
        {
            "id": guild.id,
            "name": guild.name,
            "member_count": guild.member_count,
            "owner_id": guild.owner_id
        }
        for guild in bot_instance.guilds
    ]
    
    return jsonify({"guilds": guilds, "count": len(guilds)})

@app.route('/api/invite', methods=['GET'])
def api_invite():
    """Generate bot invite link"""
    if bot_instance is None or bot_instance.user is None:
        return jsonify({"error": "Bot not online"}), 503
    
    # Standard permissions: Administrator (8)
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot_instance.user.id}&permissions=8&scope=bot"
    
    return jsonify({
        "invite_url": invite_url,
        "bot_id": bot_instance.user.id
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint (for AWS Load Balancer)"""
    return jsonify({"status": "healthy"}), 200

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Not found", "message": str(error)}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error", "message": str(error)}), 500

# ============================================
# RUN FUNCTION
# ============================================

def run_web_server(bot, port=5000, host='0.0.0.0'):
    """
    Run the Flask web server
    
    Args:
        bot: Discord bot instance
        port: Port to run on (default 5000)
        host: Host to bind to (0.0.0.0 = all interfaces)
    """
    set_bot(bot)
    print(f"🌐 Starting web server on {host}:{port}")
    # Use debug=False for production
    app.run(host=host, port=port, debug=False, use_reloader=False)
