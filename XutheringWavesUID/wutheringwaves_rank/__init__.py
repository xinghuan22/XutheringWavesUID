from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .draw_rank_card import draw_rank_img
from .draw_all_rank_card import draw_all_rank_card
from .draw_rank_list_card import draw_rank_list
from .draw_total_rank_card import draw_total_rank
from ..utils.char_info_utils import PATTERN
from ..utils.name_resolve import resolve_char
from ..utils.name_convert import char_name_to_char_id
from ..utils.damage.modal import get_modal_key_by_name

sv_waves_rank_list = SV("ww角色排行", priority=3)
sv_waves_rank_all_list = SV("ww角色总排行", priority=1)
sv_waves_rank_total_list = SV("ww练度总排行", priority=0)
sv_waves_rank_local_list = SV("ww练度排行", priority=0)


@sv_waves_rank_list.on_regex(
    rf"^(?P<char>{PATTERN})(?:排行|排行榜|排名|ph|pm)$",
    block=True,
    to_ai="""查询本群某角色的排行（伤害或评分），仅群聊可用。

当用户在群里问「<角色>排行 / <角色>评分排行 / 群里谁<角色>最强」时调用。
text 必须是 "<角色名>排行" 或 "<角色名>评分排行"。
名字中含「评分」/「pf」/「练度」会走评分模式，否则走伤害模式。

私聊会被拒绝。

Args:
    text: "<角色名>排行" / "<角色名>评分排行"。例: "长离排行"、"椿评分排行"。
""",
)
async def send_rank_card(bot: Bot, ev: Event):
    if not ev.group_id:
        return await bot.send("请在群聊中使用")

    char = ev.regex_dict.get("char")

    rank_type = "伤害"
    if "综合" in char:
        rank_type = "综合评分"
    elif "评分" in char or "pf" in char or "练度" in char:
        rank_type = "评分"

    char = (
        char.replace("综合评分", "").replace("综合", "")
        .replace("伤害", "").replace("评分", "").replace("pf", "")
        .replace("练度", "").replace("本群", "").replace("群", "")
    )

    from ..wutheringwaves_config import PREFIX, WutheringWavesConfig
    if rank_type in ("伤害", "综合评分") and not WutheringWavesConfig.get_config("WavesToken").data:
        rank_type = "评分"

    res = None
    canonical_cmd = None
    if char:
        res = resolve_char(char)
        if not res.ok:
            return await bot.send(res.fail_msg())
        char = res.matched
        if rank_type == "评分":
            canonical_cmd = f"{PREFIX}{char}评分排行"
        elif rank_type == "综合评分":
            canonical_cmd = f"{PREFIX}{char}综合评分排行"
        else:
            canonical_cmd = f"{PREFIX}{char}排行"

    im = await draw_rank_img(bot, ev, char, rank_type)

    if isinstance(im, str):
        at_sender = True if ev.group_id else False
        await bot.send(res.with_tip(im, canonical_cmd) if res else im, at_sender)
    elif isinstance(im, bytes):
        await bot.send(res.wrap(im, canonical_cmd) if res else im)


@sv_waves_rank_all_list.on_regex(
    rf"^(?P<char>{PATTERN})(?:总排行|总排行榜|总排名|zph|zpm)(?P<pages>\d+)?(?P<modal>\S+)?$",
    block=True,
    to_ai="""查询全体某角色的排行（伤害或评分，跨群）。

当用户问「<角色>总排行 / 全体<角色>最强」时调用。
text 是 "<角色名>总排行<页码?>"，页码 1-50（默认 1）。名字中含「评分」/「练度」走评分模式。

Args:
    text: 例: "长离总排行1" / "椿评分总排行" / "忌炎总排行3"。
""",
)
async def send_all_rank_card(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    pages = ev.regex_dict.get("pages")

    if pages:
        pages = int(pages)
    else:
        pages = 1

    if pages > 50:
        pages = 50
    elif pages < 1:
        pages = 1

    rank_type = "伤害"
    if "综合" in char:
        rank_type = "综合评分"
    elif "评分" in char or "练度" in char:
        rank_type = "评分"
    char = char.replace("综合评分", "").replace("综合", "").replace("伤害", "").replace("评分", "").replace("练度", "")

    res = None
    canonical_cmd = None
    if char:
        res = resolve_char(char)
        if not res.ok:
            return await bot.send(res.fail_msg())
        char = res.matched
        from ..wutheringwaves_config import PREFIX
        if rank_type == "评分":
            canonical_cmd = f"{PREFIX}{char}评分总排行"
        elif rank_type == "综合评分":
            canonical_cmd = f"{PREFIX}{char}综合评分总排行"
        else:
            canonical_cmd = f"{PREFIX}{char}总排行"

    modal = ""
    modal_text = ev.regex_dict.get("modal")
    if modal_text and char:
        cid = char_name_to_char_id(char)
        if cid:
            modal = get_modal_key_by_name(int(cid), modal_text)
    im = await draw_all_rank_card(bot, ev, char, rank_type, pages, modal)

    if isinstance(im, str):
        at_sender = True if ev.group_id else False
        await bot.send(res.with_tip(im, canonical_cmd) if res else im, at_sender)
    elif isinstance(im, bytes):
        await bot.send(res.wrap(im, canonical_cmd) if res else im)


@sv_waves_rank_total_list.on_regex(
    r"^(练度总排行|练度总排行榜|练度总排名|ldzph|ldzpm)(?P<pages>\d+)?$",
    block=True,
    to_ai="""查询全体练度总排行（账号综合练度评分跨群）。

当用户问「练度总排行 / 全体练度最强」时调用。
text 是 "练度总排行<页码?>"，页码 1-50。

Args:
    text: 例: "练度总排行1" / "ldzph2"。
""",
)
async def send_total_rank_card(bot: Bot, ev: Event):
    pages = ev.regex_dict.get("pages")

    if pages:
        pages = int(pages)
    else:
        pages = 1

    if pages > 50:
        pages = 50
    elif pages < 1:
        pages = 1

    im = await draw_total_rank(bot, ev, pages)
    await bot.send(im)


@sv_waves_rank_local_list.on_command(
    ("练度排行", "群练度排行", "练度群排行", "练度群排行榜", "练度排名", "群练度排名", "练度群排名", "ldph", "ldpm"),
    block=True,
    to_ai="""查询本群练度排行（按账号综合练度评分），仅群聊可用。

当用户在群里问「群里谁练度最高 / 练度排行」时调用。
text 可附评级筛选 a / s / ss，留空看全部。

私聊会被拒绝。

Args:
    text: 可选 "a" / "s" / "ss" 评级筛选。
""",
)
async def send_rank_list_card(bot: Bot, ev: Event):
    if not ev.group_id:
        return await bot.send("请在群聊中使用")

    im = await draw_rank_list(bot, ev)
    await bot.send(im)
