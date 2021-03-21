from .filterchecker import FilterChecker


async def setup(bot):
    cog = FilterChecker(bot)
    bot.add_cog(cog)