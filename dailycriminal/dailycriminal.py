import discord

from redbot.core import commands, checks, modlog, Config
from discord.ext import tasks
from datetime import datetime, timedelta

import logging

from collections import deque

log = logging.getLogger("even.dailycriminal")

class DailyCriminal(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.dc_ender.start()

        self.bad_log = deque([], maxlen=5)

        self.config = Config.get_conf(self, identifier=13376942096)

        default_member = {
            "count": 0,
            "status": 0,
            "end_time": None,
        }

        default_guild_config = {
            "role": None,
        }

        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild_config)


    async def initialize(self):
        await self.register_casetypes()


    @staticmethod
    async def register_casetypes():
        dc_case = {
            "name": "dc",
            "default_setting": True,
            "image": "\N{SPEAKER WITH CANCELLATION STROKE}",
            "case_str": "Daily Criminal",
        }
        perm_dc_case = {
            "name": "permdc",
            "default_setting": True,
            "image": "\N{SPEAKER WITH CANCELLATION STROKE}",
            "case_str": "Permanent Daily Criminal",
        }

        try:
            await modlog.register_casetype(**dc_case)
            await modlog.register_casetype(**perm_dc_case)
        except RuntimeError:
            pass

    def cog_unload(self):
        self.dc_ender.cancel()

    def map_count_to_timedelta(self, count):
        if count < 1:
            return timedelta(minutes=1)
        elif count == 1:
            return timedelta(days=3)
        elif count == 2:
            return timedelta(days=7)
        elif count == 3:
            return timedelta(days=30)
        else:
            return timedelta(days=1000)

    @commands.group()
    @checks.mod_or_permissions(administrator=True)
    async def dcset(self, ctx):
        pass

    @dcset.command()
    @checks.mod_or_permissions(administrator=True)
    async def role(self, ctx, role: commands.RoleConverter):
        """
        Set the role to be used for daily criminal.
        """
        await self.config.guild(ctx.guild).role.set(role.id)
        await ctx.send(f"Daily criminal role set to: {role.name}")


    @dcset.command()
    @checks.mod_or_permissions(administrator=True)
    async def log(self, ctx, pos: int):
        """
        Set the role to be used for daily criminal.
        """
        if pos < 0 or pos > 5:
            return
        await ctx.send("```" + self.bad_log[pos] + "```")


    @commands.group(invoke_without_command=True)
    @checks.mod_or_permissions(administrator=True)
    async def dc(self, ctx, member: commands.MemberConverter, *, reason):
        """
        Give a member the daily criminal role, aliases to "dc give".
        """
        await self.give(ctx, member, reason=reason)

    @dc.command()
    @checks.mod_or_permissions(administrator=True)
    async def give(self, ctx, member: commands.MemberConverter, *, reason: str = None):
        """
        Give a member the daily criminal role.
        """
        roleid = await self.config.guild(ctx.guild).role()
        if not roleid:
            return await ctx.send("A daily criminal role has not been set.")
        role = ctx.guild.get_role(roleid)

        stored_member_info = self.config.member(member)
        status = await stored_member_info.status()
        if status == 0:
            # Give the DC role
            try:
                await member.add_roles(role, reason="Daily criminal")
            except discord.Forbidden:
                return await ctx.send("Missing permissions")

            # Update status and dc count
            c = await stored_member_info.count()
            await stored_member_info.count.set(int(c) + 1)
            if c > 2:
                await stored_member_info.status.set(3)
                dc_type = "permdc"
            else:
                await stored_member_info.status.set(1)
                dc_type = "dc"

            # Make a modlog case
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type=dc_type,
                user=member, moderator=ctx.author, reason=reason)

            await ctx.send("User given daily criminal")
        elif status == 1:
            await ctx.send("User already has daily criminal")
        elif status == 2:
            await ctx.send("User is on daily criminal countdown")
        else:
            await ctx.send("User has permanent daily criminal")


    @dc.command()
    @checks.mod_or_permissions(administrator=True)
    async def start(self, ctx, member: commands.MemberConverter):
        """
        Start the daily criminal countdown for a member.
        """        
        stored_member_info = self.config.member(member)
        status = await stored_member_info.status()

        if status == 1:
            count = await stored_member_info.count()            
            now = datetime.now()
            duration = self.map_count_to_timedelta(count)

            # Update status
            await stored_member_info.end_time.set(datetime.timestamp(now + duration))
            await stored_member_info.status.set(2)
            await ctx.send("Daily criminal countdown started")
        elif status == 2:
            await ctx.send("User already has active countdown")
        elif status == 3:
            await ctx.send("User has permanent daily criminal")
        else:
            await ctx.send("User not in daily criminals")


    @dc.command()
    @checks.mod_or_permissions(administrator=True)
    async def end(self, ctx, member: commands.MemberConverter, updated_count: int=None):
        """
        End the daily criminal countdown for a member early. Optional argument to set the daily criminal counter.
        """
        stored_member_info = self.config.member(member)
        status = await stored_member_info.status()

        roleid = await self.config.guild(ctx.guild).role()
        if not roleid:
            return await ctx.send("A daily criminal role has not been set.")
        role = ctx.guild.get_role(roleid)

        if updated_count is not None:
            await stored_member_info.count.set(updated_count)
            await ctx.send(f"Daily criminal count set to {updated_count}")

        if status == 1 or status == 2 or status == 3:
            try:
                await member.remove_roles(role, reason="DC end")
            except (discord.Forbidden, discord.HTTPException):
                return
            
            await stored_member_info.status.set(0)
            await stored_member_info.end_time.set(None)

            await ctx.send(f"DC ended for {member.name}")
        else:
            await ctx.send(f"{member.name} does not have daily criminal.")


    @dc.command()
    @checks.mod_or_permissions(administrator=True)
    async def status(self, ctx, member: commands.MemberConverter):
        """
        Chech the daily criminal status for a member.
        """
        stored_member_info = await self.config.member(member)()

        embed = discord.Embed(title=f"DC status for {member} ({member.id})")
        embed = embed.add_field(name="DC count", value=stored_member_info["count"])

        status = stored_member_info["status"]
        if status == 0:
            embed = embed.add_field(name="Status", value="Not daily criminal")
        if status == 1:
            embed = embed.add_field(name="Status", value="Given daily criminal")
        if status == 2:
            embed = embed.add_field(name="Status", value="In daily criminal countdown")
            end = datetime.fromtimestamp(stored_member_info["end_time"])
            embed = embed.add_field(name="End time", value=end.strftime("%Y-%m-%d %H:%M"), inline=False)

            diff = (end - datetime.now()).total_seconds()
            remaining_days = int(diff)//(3600 * 24)
            remaining_hours = int(diff - 3600 * 24 * remaining_days)//3600
            remaining_minutes = int(diff - 3600 * 24 * remaining_days - remaining_hours * 3600)//60
            embed = embed.add_field(name="Remaining", value=f"{remaining_days}d {remaining_hours}h {remaining_minutes}m", inline=False)

        if status == 3:
            embed = embed.add_field(name="Status", value="Permanent daily criminal")

        await ctx.send(embed=embed)


    @tasks.loop(seconds=60.0)
    async def dc_ender(self):
        try:

            get_members = self.config.all_members
            all_members = await get_members()

            now = datetime.now()
            for guild, members in all_members.items():
                guild = self.bot.get_guild(guild)
                if guild is None:
                    guild = await self.bot.fetch_guild(guild)
                    if guild is None:
                        continue
                roleid = await self.config.guild(guild).role()
                if not roleid:
                    continue
                role = guild.get_role(roleid)

                for member_id, info in members.items():
                    if info['status'] == 2:
                        end = datetime.fromtimestamp(info['end_time'])
                        if now > end:
                            member = guild.get_member(member_id)
                            if member is None:
                                member = await guild.fetch_member(member_id)

                            member_info = self.config.member(member)
                            await member.remove_roles(role, reason="DC end")
                            await member_info.status.set(0)
                            await member_info.end_time.set(None)
        except Exception as e:
            log.exception("Error removing roles")
            self.bad_log.appendleft(str(e))

