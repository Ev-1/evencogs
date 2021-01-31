from .dailycriminal import DailyCriminal


async def setup(bot):
    cog = DailyCriminal(bot)
    await cog.initialize()
    bot.add_cog(cog)