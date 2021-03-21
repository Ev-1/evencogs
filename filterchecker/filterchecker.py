import discord

from redbot.core import commands, checks, modlog, Config
from discord.ext import tasks
from datetime import datetime, timedelta

import logging

from collections import deque

class FilterChecker(commands.Cog):
    """Cog for checking why messages got filtered"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="checkfilter")
    async def filtercheck(self, ctx, * , message):
        filter_cfg = Config.get_conf(None, identifier=4766951341, cog_name="filter")
        filtered_words = await filter_cfg.guild(ctx.guild).filter()

        filtered = False
        comment = message

        if filtered_words:
            for word in filtered_words:
                if word in comment:
                    await ctx.send(word)
                    filtered = True
                    comment = comment.replace(word, '█'*len(word))

        if filtered:
            await ctx.send(comment)
        else:
            await ctx.send('No words filtered')
