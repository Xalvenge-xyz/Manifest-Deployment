from dotenv import load_dotenv
import os
import discord
from discord import app_commands
from discord.ext import commands
from status_bot import StatusMonitor
import requests
from keep_alive import keep_alive
from io import BytesIO
from status_bot import StatusMonitor, create_setting_command
from game_monitor import GameMonitor, create_gamesetup_command
from game_monitor import (
    GameMonitor,
    create_gamesetup_command,
    create_gamelist_command,
    create_testgamealerts_command,
    create_newgame_command,
    create_fixegame_command,
    create_gamesearch_command,
    create_updategame_command,
    # create_resetgames_command
)
 
load_dotenv()
keep_alive() 
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)

    # Instantiate the monitors
    monitor = StatusMonitor(bot)
    game_monitor = GameMonitor(bot)

    # Status monitor commands
    bot.tree.add_command(create_setting_command(monitor), guild=guild)

    # Game monitor commands (owner only)
    bot.tree.add_command(create_gamesetup_command(game_monitor), guild=guild)
    bot.tree.add_command(create_testgamealerts_command(game_monitor), guild=guild)
    # bot.tree.add_command(create_resetgames_command(game_monitor), guild=guild)
    bot.tree.add_command(create_newgame_command(game_monitor), guild=guild)
    bot.tree.add_command(create_fixegame_command(game_monitor), guild=guild)
    bot.tree.add_command(create_updategame_command(game_monitor), guild=guild)

    # Public command for everyone
    bot.tree.add_command(create_gamelist_command(game_monitor), guild=guild)
    bot.tree.add_command(create_gamesearch_command(game_monitor), guild=guild)
    # Sync commands
    await bot.tree.sync(guild=guild)

    print(f"{bot.user} is online and commands are synced!")


def get_steam_info(appid):
    """Fetch Steam game name + image URL."""
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
        data = requests.get(url).json()

        if not data[str(appid)]["success"]:
            return None

        info = data[str(appid)]["data"]
        return {
            "name": info.get("name", "Unknown Game"),
            "image": info.get("header_image", None)
        }

    except:
        return None


@bot.tree.command(name="manifest", description="Get a Steam manifest file with game info")
@app_commands.describe(appid="Enter the Steam App ID")
async def manifest(interaction: discord.Interaction, appid: str):
    if not appid.isdigit():
        await interaction.response.send_message("❌ App ID must be numbers only!", ephemeral=True)
        return

    # Step 1: Send initial message to avoid Unknown interaction
    await interaction.response.send_message("⏳ Fetching manifest, please wait...", ephemeral=True)

    # Step 2: Get Steam info
    info = get_steam_info(appid)
    if not info:
        await interaction.edit_original_response(content="❌ Game not found on Steam.")
        return

    game_name = info["name"]
    game_image = info["image"]

    file_bytes = BytesIO()

    # Step 3: Playwright fetch wrapped in timeout
    try:
        async def fetch_manifest():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=True
                )
                page = await context.new_page()
                await page.goto("https://manifestor.cc/", wait_until="networkidle")
                await page.fill("input[type='text']", appid)

                # Click button & catch download
                async with page.expect_download() as dl_info:
                    await page.click("button[type='submit']")  # <-- adjust selector if needed

                download = await dl_info.value
                data = await download.read_bytes()
                file_bytes.write(data)
                file_bytes.seek(0)

                await context.close()
                await browser.close()

        await asyncio.wait_for(fetch_manifest(), timeout=30)  # 30s timeout

    except asyncio.TimeoutError:
        await interaction.edit_original_response("❌ Fetching manifest timed out. Please try again later.")
        return
    except Exception as e:
        await interaction.edit_original_response(f"❌ Failed to fetch manifest:\n```{e}```")
        return

    # Step 4: Create Discord embed
    embed = discord.Embed(
        title=f"🎮 {game_name}",
        description=f"📦 **Manifest for App ID:** `{appid}`",
        color=discord.Color.blurple()
    )
    if game_image:
        embed.set_image(url=game_image)
    embed.set_footer(text="Steam manifest bot by JAY XALVENGE")

    # Step 5: Edit original response with embed + file
    await interaction.edit_original_response(
        content=None,
        embed=embed,
        file=discord.File(file_bytes, filename=f"{appid}.lua")
    )

bot.run(TOKEN)