import os
from datetime import datetime

from flask import Flask, jsonify, render_template

app = Flask(__name__, template_folder="templates")

bot_instance = None


def set_bot(bot):
    """Attach the Discord bot instance so the dashboard can read status."""
    global bot_instance
    bot_instance = bot


@app.route("/", methods=["GET"])
def index():
    """Main webpage for the bot dashboard."""
    return render_template("index.html", bot_online=(bot_instance is not None))


@app.route("/health", methods=["GET"])
def health():
    """Load balancer / uptime health check."""
    return jsonify({"status": "healthy"}), 200


@app.route("/api/status", methods=["GET"])
def api_status():
    """Return a small JSON payload for status checks and the dashboard."""
    if bot_instance is None:
        return jsonify({"status": "offline", "message": "Bot not initialized"}), 503

    bot_user = bot_instance.user
    uptime = "Unknown"
    if hasattr(bot_instance, "start_time"):
        uptime = str(datetime.utcnow() - bot_instance.start_time)

    return jsonify({
        "status": "online",
        "bot_name": bot_user.name if bot_user else "Unknown",
        "bot_id": bot_user.id if bot_user else None,
        "guilds": len(bot_instance.guilds),
        "uptime": uptime,
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/api/commands", methods=["GET"])
def api_commands():
    """List command names for the dashboard or external clients."""
    if bot_instance is None:
        return jsonify({"error": "Bot not online"}), 503

    commands = []
    for command in bot_instance.commands:
        commands.append({
            "name": command.name,
            "description": command.help or "No description",
            "usage": str(command),
        })

    return jsonify({"commands": commands, "count": len(commands)})


@app.route("/api/guilds", methods=["GET"])
def api_guilds():
    """List guilds the bot is connected to."""
    if bot_instance is None:
        return jsonify({"error": "Bot not online"}), 503

    guilds = [
        {
            "id": guild.id,
            "name": guild.name,
            "member_count": guild.member_count,
            "owner_id": guild.owner_id,
        }
        for guild in bot_instance.guilds
    ]

    return jsonify({"guilds": guilds, "count": len(guilds)})


@app.route("/api/invite", methods=["GET"])
def api_invite():
    """Generate a Discord bot invite URL using the same bot id."""
    if bot_instance is None or bot_instance.user is None:
        return jsonify({"error": "Bot not online"}), 503

    invite_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={bot_instance.user.id}"
        "&permissions=8&scope=bot"
    )

    return jsonify({"invite_url": invite_url, "bot_id": bot_instance.user.id})


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found", "message": str(error)}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error", "message": str(error)}), 500


def run_web_server(bot, port=5000, host="0.0.0.0"):
    """Run the Flask app in a background thread so the bot and web page work together."""
    set_bot(bot)
    print(f"🌐 Starting web server on {host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_web_server(None)
