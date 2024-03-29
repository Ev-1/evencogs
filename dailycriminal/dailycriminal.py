import discord

from redbot.core import commands, checks, modlog, Config, utils
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
            "reason": "",
        }

        default_guild_config = {
            "role": None,
            "channel": None,
            "dc_info_message": None,
        }

        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild_config)

        self.bot_initialized = False
        self.not_in_server = []

        self.loop_index = 0


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
    async def channel(self, ctx, channel: commands.TextChannelConverter):
        """
        Set the channel to be used for daily criminal info.
        """
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Daily criminal info channel role set to: {channel.mention}")

    @dcset.command()
    @checks.mod_or_permissions(administrator=True)
    async def message(self, ctx, message: str):
        """
        Set the message to be sent to users receiving daily criminal.
        """
        await self.config.guild(ctx.guild).dc_info_message.set(message)
        await ctx.send(f"Daily criminal DM info message set to: {message}")

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
        Send the most recent logged errors in chat.
        """
        if pos < 0 or pos > 5:
            return
        try:
            await ctx.send("```" + self.bad_log[pos] + "```")
        except:
            await ctx.send("No logs")

    @dcset.command(name="check")
    @checks.mod_or_permissions(administrator=True)
    async def _check(self, ctx):
        await ctx.send("Checking daily criminals...")
        get_members = self.config.all_members
        all_members = await get_members()

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
                try:
                    if info['status'] == 2:
                        end = datetime.fromtimestamp(info['end_time'])
                        if int((end - datetime.now()).total_seconds()) < 0:
                            member = guild.get_member(member_id)
                            if member is None:
                                member = await guild.fetch_member(member_id)

                            if member is None:
                                self.not_in_server.append(member_id)

                            member_info = self.config.member(member)
                            await member.remove_roles(role, reason="DC end")
                            await member_info.status.set(0)
                            await member_info.end_time.set(None)
                except Exception as e:
                    await ctx.send(str(e) + f" Failed for {member_id}")
        await ctx.send("Checked")

    @commands.command()
    async def dcstatus(self, ctx):
        """
        Sends you a direct message with information about your daily criminal status
        """
        if ctx.guild is None:
            return await ctx.send("This command does not work in direct messages")
        embed = await self.get_status_embed(ctx.author)
        channelid = await self.config.guild(ctx.guild).channel()
        if channelid is not None:
            channel = ctx.guild.get_channel(channelid) or await self.bot.fetch_channel(channelid)
            embed.description = f"Read {channel.mention} for info about daily criminal"
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.channel.send(f"I can't send you direct messages {ctx.author.mention}")

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
            await stored_member_info.reason.set(reason)
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

            dc_info_message = await self.config.guild(ctx.guild).dc_info_message()
            if dc_info_message:
                try:
                    await member.send(dc_info_message)
                except discord.Forbidden:
                    await ctx.send("Failed to send DM to user")

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
            await ctx.send("Daily criminal countdown started. It will be removed in: " + self.format_time_dhm(duration))
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
            await stored_member_info.reason.set("")

            await ctx.send(f"DC ended for {member.name}")
        else:
            await ctx.send(f"{member.name} does not have daily criminal.")

    def remaining_time_string(self, end_time):
        if end_time is None:
            return "-"
        if isinstance(end_time, float):
            end_time = datetime.fromtimestamp(end_time)
        return self.format_time_dhm(end_time - datetime.now())

    def format_time_dhm(self, delta: timedelta):
        diff = int(delta.total_seconds())
        prefix = ""
        if diff < 0:
            prefix = "-"
            diff = -diff
        remaining_days = int(diff)//(3600 * 24)
        remaining_hours = int(diff - 3600 * 24 * remaining_days)//3600
        remaining_minutes = int(diff - 3600 * 24 * remaining_days - remaining_hours * 3600)//60
        return f"{prefix}{remaining_days}d {remaining_hours}h {remaining_minutes}m"

    @dc.command()
    @checks.mod_or_permissions(administrator=True)
    async def status(self, ctx, member: commands.MemberConverter = None):
        """
        Chech the daily criminal status for a member.
        """
        # stored_member_info = await self.config.member(member)()
        embed = await self.get_status_embed(member)
        await ctx.send(embed=embed)

    async def get_status_embed(self, member):
        stored_member_info = await self.config.member(member)()

        embed = discord.Embed(title=f"DC status for {member} ({member.id})")
        embed = embed.add_field(name="DC count", value=stored_member_info["count"])

        status = stored_member_info["status"]
        reason = stored_member_info.get("reason") or "No reason registered"
        if status == 0:
            embed = embed.add_field(name="Status", value="Not daily criminal")
        if status == 1:
            embed = embed.add_field(name="Status", value="Given daily criminal")
            embed = embed.add_field(name="Reason", value=reason)
        if status == 2:
            embed = embed.add_field(name="Status", value="In daily criminal countdown")
            end = datetime.fromtimestamp(stored_member_info["end_time"])
            embed = embed.add_field(name="End time", value=end.strftime("%Y-%m-%d %H:%M") + "(UTC)", inline=False)
            embed = embed.add_field(name="Remaining", value=self.remaining_time_string(end), inline=False)
            embed = embed.add_field(name="Reason", value=reason)
        if status == 3:
            embed = embed.add_field(name="Status", value="Permanent daily criminal")
            embed = embed.add_field(name="Reason", value=reason)
        
        return embed

    @dc.command(name="list")
    @checks.mod_or_permissions(administrator=True)
    async def _list(self, ctx, include_all: bool=False):
        members = await self.config.all_members()
        guild_members = members[ctx.guild.id]
        memberlist = []
        for member, stats in guild_members.items():
            if stats['status'] and member not in self.not_in_server:
                if include_all or stats['end_time'] is not None:
                    memberlist.append({'memberid': member, **stats})

        memberlist.sort(key=lambda m: m['end_time'] if m['end_time'] else float(1e20))

        def pad_str(to_add: str, width: int=25) -> str:
            if width-len(to_add) > 0:
                return to_add + " "*(width-len(to_add))
            return to_add

        out_strs = []
        out = pad_str("User ID") + pad_str("Count", width=15) + pad_str("Status", width=20) + \
                  pad_str("Remaining time", width=15) + "\n"

        for m in memberlist:
            n = pad_str(f"{m['memberid']}")
            n += pad_str(f"{m['count']}", width=15)
            n += pad_str(f"{'Given role' if m['status'] == 1 else 'In countdown'}", width=20)
            n += pad_str(f"{self.remaining_time_string(m['end_time'])}", width=15)
            n += "\n"
            if len(n) + len(out) + 7 > 2000:
                out_strs.append(out)
                out = n
            else:
                out += n
        out_strs.append(out)
        
        for o in out_strs:
            await ctx.send("```\n" + o + "```")


    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            self.not_in_server.remove(member.id)
        except ValueError:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        self.not_in_server.append(member.id)

    @tasks.loop(minutes=2.0)
    async def dc_ender(self):
        get_members = self.config.all_members
        all_members = await get_members()


        self.loop_index = (self.loop_index + 1) % 10

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
                # Check members not in the server every once in a while
                if (self.loop_index == 0) or (member_id not in self.not_in_server):
                    try:
                        if info['status'] == 2:
                            end = datetime.fromtimestamp(info['end_time'])
                            if int((end - datetime.now()).total_seconds()) < 0:
                                member = guild.get_member(member_id)
                                if member is None:
                                    try:
                                        member = await guild.fetch_member(member_id)
                                    except discord.HTTPException:
                                        member = None

                                if member is None:
                                    self.not_in_server.append(member_id)

                                member_info = self.config.member(member)
                                await member.remove_roles(role, reason="DC end")
                                await member_info.status.set(0)
                                await member_info.end_time.set(None)
                    except Exception as e:
                        log.exception("Error removing roles")
                        self.bad_log.appendleft(str(e))

    @dc_ender.before_loop
    async def before_dc_ender(self):
        await self.bot.wait_until_ready()
