from dotenv import load_dotenv
import os
import discord
from discord import app_commands
from discord.ext import commands
from status_bot import StatusMonitor
import requests
from keep_alive import keep_alive
from playwright.async_api import async_playwright
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
        await interaction.response.send_message(
            "❌ App ID must be numbers only!", ephemeral=True
        )
        return

    # Defer interaction (acknowledge and give bot time)
    await interaction.response.defer()

    # Get Steam info (game name + image)
    info = get_steam_info(appid)
    if not info:
        await interaction.followup.send("❌ Game not found on Steam.")
        return

    game_name = info["name"]
    game_image = info["image"]

    file_bytes = BytesIO()  # prepare in-memory file

    try:
        # --- Playwright section ---
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Navigate to Manifestor
            await page.goto("https://manifestor.cc/")

            # Wait for AppID input field to appear
            await page.wait_for_selector("input[type='text']")

            # Fill AppID
            await page.fill("input[type='text']", appid)

            # Intercept download
            async with page.expect_download() as download_info:
                # Click the "Get Manifest" button
                await page.click("button")  # <-- Replace with the actual button selector
            download = await download_info.value
            file_path = await download.path()

            # Read the Lua file
            with open(file_path, "rb") as f:
                file_bytes.write(f.read())
            file_bytes.seek(0)

            await browser.close()
        # --- End Playwright section ---

        # Create embed
        embed = discord.Embed(
            title=f"🎮 {game_name}",
            description=f"📦 **Manifest for App ID:** `{appid}`",
            color=discord.Color.blurple()
        )
        if game_image:
            embed.set_image(url=game_image)
        embed.set_footer(text="Steam game bot • Powered by JAY CAPARIDA AKA XALVENGE D.")

        # Send the Lua file
        await interaction.followup.send(
            embed=embed,
            file=discord.File(file_bytes, filename=f"{appid}.lua")
        )

    except Exception as e:
        # Handle timeout / interaction expired gracefully
        await interaction.followup.send(
            f"❌ Failed to fetch manifest. Error: {e}", ephemeral=True
        )



bot.run(TOKEN)