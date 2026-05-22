import os
import random
import string
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
QUEUE_CHANNEL_ID = int(os.getenv("QUEUE_CHANNEL_ID"))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

teams = {}
team_queue = []


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def get_user_team(user_id):
    for code, team in teams.items():
        if user_id in team["members"]:
            return code, team
    return None, None


async def create_match_channel(interaction, team1_code, team2_code):
    guild = interaction.guild
    team1 = teams[team1_code]
    team2 = teams[team2_code]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    all_players = team1["members"] + team2["members"]

    for member_id in all_players:
        member = guild.get_member(member_id)
        if member:
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

    channel = await guild.create_text_channel(
        name=f"match-{team1['mode']}-{team1_code}-vs-{team2_code}",
        overwrites=overwrites
    )

    mentions1 = " ".join([f"<@{x}>" for x in team1["members"]])
    mentions2 = " ".join([f"<@{x}>" for x in team2["members"]])

    await channel.send(
        f"🔥 **MATCH FOUND**\n\n"
        f"👥 Team `{team1_code}`: {mentions1}\n"
        f"⚔ VS\n"
        f"👥 Team `{team2_code}`: {mentions2}\n\n"
        f"🎮 Mode: **{team1['mode']}**"
    )

    team1["queued"] = False
    team2["queued"] = False

    if team1_code in team_queue:
        team_queue.remove(team1_code)
    if team2_code in team_queue:
        team_queue.remove(team2_code)

    return channel


class CreateTeamModal(discord.ui.Modal, title="Create Team"):
    mode = discord.ui.TextInput(
        label="Mode",
        placeholder="Ex: 1v1, 2v2, 3v3, 4v4",
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        mode = self.mode.value.lower().strip()

        if mode not in ["1v1", "2v2", "3v3", "4v4"]:
            await interaction.response.send_message("❌ Mode invalid. Folosește 1v1, 2v2, 3v3 sau 4v4.", ephemeral=True)
            return

        old_code, old_team = get_user_team(user.id)
        if old_team:
            await interaction.response.send_message(f"❌ Ești deja în teamul `{old_code}`.", ephemeral=True)
            return

        size = int(mode[0])
        code = generate_code()

        teams[code] = {
            "leader": user.id,
            "members": [user.id],
            "names": [user.display_name],
            "mode": mode,
            "size": size,
            "queued": False
        }

        await interaction.response.send_message(
            f"✅ **Team creat!**\n"
            f"🎮 Mode: **{mode}**\n"
            f"🔑 Cod team: `{code}`\n\n"
            f"Dă codul prietenilor tăi. Ei apasă pe **Join Team**.",
            ephemeral=True
        )


class JoinTeamModal(discord.ui.Modal, title="Join Team"):
    code = discord.ui.TextInput(
        label="Cod Team",
        placeholder="Ex: A1B2C3",
        max_length=6
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        code = self.code.value.upper().strip()

        if code not in teams:
            await interaction.response.send_message("❌ Cod invalid.", ephemeral=True)
            return

        old_code, old_team = get_user_team(user.id)
        if old_team:
            await interaction.response.send_message("❌ Ești deja într-un team.", ephemeral=True)
            return

        team = teams[code]

        if len(team["members"]) >= team["size"]:
            await interaction.response.send_message("❌ Teamul este full.", ephemeral=True)
            return

        team["members"].append(user.id)
        team["names"].append(user.display_name)

        await interaction.response.send_message(
            f"✅ Ai intrat în teamul `{code}`.\n"
            f"Players: **{len(team['members'])}/{team['size']}**",
            ephemeral=True
        )


class QueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👥 Create Team", style=discord.ButtonStyle.blurple)
    async def create_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateTeamModal())

    @discord.ui.button(label="🔑 Join Team", style=discord.ButtonStyle.blurple)
    async def join_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(JoinTeamModal())

    @discord.ui.button(label="⚔ Queue Team", style=discord.ButtonStyle.green)
    async def queue_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        code, team = get_user_team(user.id)

        if not team:
            await interaction.response.send_message("❌ Nu ai team.", ephemeral=True)
            return

        if team["leader"] != user.id:
            await interaction.response.send_message("❌ Doar liderul poate băga teamul în queue.", ephemeral=True)
            return

        if len(team["members"]) < team["size"]:
            await interaction.response.send_message(
                f"❌ Teamul nu este complet. Ai {len(team['members'])}/{team['size']} playeri.",
                ephemeral=True
            )
            return

        if team["queued"]:
            await interaction.response.send_message("❌ Teamul este deja în queue.", ephemeral=True)
            return

        for enemy_code in team_queue:
            enemy_team = teams[enemy_code]

            if enemy_team["mode"] == team["mode"] and enemy_code != code:
                channel = await create_match_channel(interaction, code, enemy_code)

                await interaction.response.send_message(
                    f"🔥 Match găsit! Canal creat: {channel.mention}",
                    ephemeral=False
                )
                return

        team["queued"] = True
        team_queue.append(code)

        await interaction.response.send_message(
            f"✅ Teamul `{code}` a intrat în queue pentru **{team['mode']}**.",
            ephemeral=True
        )

    @discord.ui.button(label="📋 My Team", style=discord.ButtonStyle.gray)
    async def my_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        code, team = get_user_team(interaction.user.id)

        if not team:
            await interaction.response.send_message("❌ Nu ai team.", ephemeral=True)
            return

        status = "🟢 În Queue" if team["queued"] else "🔴 Nu este în Queue"

        await interaction.response.send_message(
            f"📋 **Team `{code}`**\n"
            f"🎮 Mode: **{team['mode']}**\n"
            f"👥 Players: **{len(team['members'])}/{team['size']}**\n"
            f"Status: {status}\n\n"
            + "\n".join([f"• {name}" for name in team["names"]]),
            ephemeral=True
        )

    @discord.ui.button(label="❌ Leave Team/Queue", style=discord.ButtonStyle.red)
    async def leave_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        code, team = get_user_team(user.id)

        if not team:
            await interaction.response.send_message("❌ Nu ești într-un team.", ephemeral=True)
            return

        if code in team_queue:
            team_queue.remove(code)

        if user.id == team["leader"]:
            del teams[code]
            await interaction.response.send_message("✅ Teamul a fost șters.", ephemeral=True)
            return

        team["members"].remove(user.id)

        if user.display_name in team["names"]:
            team["names"].remove(user.display_name)

        team["queued"] = False

        await interaction.response.send_message("✅ Ai ieșit din team.", ephemeral=True)


@bot.event
async def on_ready():
    print(f"✅ Santo Lpz SVR online ca {bot.user}")

    try:
        channel = await bot.fetch_channel(QUEUE_CHANNEL_ID)
    except Exception as e:
        print(f"❌ Nu pot accesa canalul: {e}")
        return

    embed = discord.Embed(
        title="🎮 Santo Lpz SVR Queue",
        description=(
            "👥 **Create Team** - faci team 1v1 / 2v2 / 3v3 / 4v4\n"
            "🔑 **Join Team** - intri cu codul primit\n"
            "⚔ **Queue Team** - cauți adversari\n"
            "📋 **My Team** - vezi teamul tău\n"
            "❌ **Leave Team/Queue** - ieși din team sau queue\n\n"
            "Când două teamuri de același mode intră în queue, botul creează canal privat automat."
        ),
        color=discord.Color.blue()
    )

    await channel.send(embed=embed, view=QueueView())


bot.run(TOKEN)