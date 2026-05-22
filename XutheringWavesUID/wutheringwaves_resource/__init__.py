import random
import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..wutheringwaves_config import WutheringWavesConfig
from ..utils.download_utils import copy_if_different, check_file_hash
from ..utils.resource.download_all_resource import (
    reload_all_modules,
    download_all_resource,
    notify_master_and_reload,
)
from ..utils.resource.RESOURCE_PATH import (
    BUILD_PATH,
    BUILD_TEMP,
    MAP_BUILD_PATH,
    MAP_BUILD_TEMP,
)

# 网页面板编辑器 (导入即注册路由 /waves/panel-edit/, 由 WavesPanelEditPassword 启停)
from . import panel_editor  # noqa: F401

RESOURCE_DOWNLOAD_TIME = WutheringWavesConfig.get_config("ResourceDownloadTime").data
if not RESOURCE_DOWNLOAD_TIME or len(RESOURCE_DOWNLOAD_TIME) != 2:
    logger.warning("[鸣潮] 资源下载时间配置异常，将不进行定时下载")
    RESOURCE_DOWNLOAD_TIME = ["-1", "-1"]
RESOURCE_DOWNLOAD_HOUR = int(RESOURCE_DOWNLOAD_TIME[0])
RESOURCE_DOWNLOAD_MINUTE = RESOURCE_DOWNLOAD_TIME[1]

sv_download_config = SV("ww资源下载", pm=1)


@sv_download_config.on_fullmatch(("强制下载全部资源", "下载全部资源", "补充资源", "刷新补充资源"))
async def send_download_resource_msg(bot: Bot, ev: Event):
    await bot.send("[鸣潮] 正在开始下载~可能需要较久的时间！请勿重复执行！")
    await download_all_resource(force="强制" in ev.raw_text)
    
    if check_file_hash(BUILD_TEMP) or check_file_hash(MAP_BUILD_TEMP):    
        await download_all_resource()
    
    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")

    if build_updated or map_updated:
        await bot.send("[鸣潮] 构建文件已更新，正在重载插件...")
        await notify_master_and_reload(notify_master=False)
        await bot.send("[鸣潮] 重载完成！")
    else:
        await reload_all_modules()
        await bot.send("[鸣潮] 下载完成！")


async def startup():
    copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")

    await reload_all_modules()  # 已有资源，先加载，不然检查资源列表太久了
    logger.info("[鸣潮] 等待资源下载完成...")
    await download_all_resource()

    logger.info("[鸣潮] 资源下载完成，开始校验...")
    if check_file_hash(BUILD_TEMP) or check_file_hash(MAP_BUILD_TEMP):
        await download_all_resource()

    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源", soft=True)
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源", soft=True)

    if build_updated or map_updated:
        logger.info("[鸣潮] 构建文件已更新，正在重载插件...")
        await notify_master_and_reload()
    else:
        await reload_all_modules()

    logger.info("[鸣潮] 资源下载完成！完成启动！")


async def auto_download_resource():
    delay_seconds = random.randint(0, 3600)
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    logger.info("[鸣潮] 定时任务: 开始下载全部资源...")
    await download_all_resource()

    if check_file_hash(BUILD_TEMP) or check_file_hash(MAP_BUILD_TEMP):    
        await download_all_resource()

    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源", soft=True)
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源", soft=True)
    if build_updated or map_updated:
        logger.info("[鸣潮] 定时任务: 构建文件已更新，正在重载插件...")
        await notify_master_and_reload("定时任务: 构建文件已更新，正在重载插件...")
    else:
        await reload_all_modules()
    logger.info("[鸣潮] 定时任务: 资源下载完成")

if 0 <= RESOURCE_DOWNLOAD_HOUR < 24 and 0 <= int(RESOURCE_DOWNLOAD_MINUTE) < 60:
    scheduler.add_job(
        auto_download_resource,
        "cron",
        id="ww_resource_download",
        hour=RESOURCE_DOWNLOAD_HOUR,
        minute=RESOURCE_DOWNLOAD_MINUTE,
    )
