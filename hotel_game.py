"""A deterministic, zero-dependency text game for blind AI play.

Only ``new_game(seed)`` and ``cmd(text)`` are public. Every returned value ends
with one compact JSON status line.
"""

import json
import os
import re
from typing import Any

__all__ = ["new_game", "cmd"]

_VERSION = 1
_DEFAULT_SEED = "lobby-light"
_SAVE_NAME = "hotel_save.json"
_GAME: dict[str, Any] | None = None
_DAYS_PER_SEASON = 7
_DAYS_PER_YEAR = _DAYS_PER_SEASON * 4

_TIME_SLOTS = ["清晨", "上午", "午后", "傍晚", "入夜", "深夜"]

_SEASONS = [
    {
        "id": "spring",
        "name": "春",
        "start": "庭院开始返青，旅馆像刚醒过来。",
        "plants": ["杏花", "蕨芽", "新苔", "山樱"],
        "animals": ["燕子", "蜜蜂", "檐下小雀", "溪边白蝶"],
        "weather": {"sun": 28, "rain": 26, "wind": 18, "fog": 12, "snow": 1},
    },
    {
        "id": "summer",
        "name": "夏",
        "start": "竹帘换成浅色，夜里会听见庭院的水声。",
        "plants": ["绣球", "薄荷", "青竹", "睡莲"],
        "animals": ["萤火虫", "蜻蜓", "树上的蝉", "池边青蛙"],
        "weather": {"sun": 32, "rain": 28, "wind": 10, "fog": 10, "snow": 0},
    },
    {
        "id": "autumn",
        "name": "秋",
        "start": "木地板变干，落叶会在门口排成一小列。",
        "plants": ["红叶", "芒草", "野菊", "熟栗"],
        "animals": ["蟋蟀", "归鸦", "松鼠", "檐下麻雀"],
        "weather": {"sun": 24, "rain": 18, "wind": 22, "fog": 22, "snow": 2},
    },
    {
        "id": "winter",
        "name": "冬",
        "start": "屋檐低低压着冷光，温泉的白汽更像灯。",
        "plants": ["山茶", "南天竹", "覆雪苔", "枯芒"],
        "animals": ["雪地足迹", "山雀", "檐角乌鸦", "柴棚旁的猫"],
        "weather": {"sun": 18, "rain": 8, "wind": 18, "fog": 12, "snow": 24},
    },
]

_LOCATIONS = {
    "front": {
        "name": "前厅",
        "aliases": ["前厅", "大厅", "柜台", "lobby", "front"],
        "look": "前厅的铃铛很轻，账本摊着，客人的伞靠在门边。",
    },
    "rooms": {
        "name": "客房",
        "aliases": ["客房", "房间", "走廊", "rooms", "room"],
        "look": "客房走廊有木地板的响声，钥匙牌按顺序垂着。",
    },
    "kitchen": {
        "name": "厨房",
        "aliases": ["厨房", "灶间", "餐食", "kitchen", "cook"],
        "look": "厨房里有米香和汤锅声，食材需要仔细盘算。",
    },
    "onsen": {
        "name": "温泉",
        "aliases": ["温泉", "汤屋", "浴场", "onsen", "spa", "bath"],
        "look": "温泉的水汽贴着竹帘，柴火决定今晚的温度。",
    },
    "garden": {
        "name": "庭院",
        "aliases": ["庭院", "院子", "后院", "garden", "yard"],
        "look": "庭院里有石灯、旧木箱和一条通往柴棚的小路。",
    },
    "shop": {
        "name": "商店",
        "aliases": ["商店", "杂货", "集市", "shop", "market"],
        "look": "街角商店挂着手写价签，老板只问你今天缺什么。",
    },
}

_LOCATION_ALIASES = {
    alias: key for key, spec in _LOCATIONS.items() for alias in spec["aliases"]
}

_WEATHERS = [
    {
        "id": "sun",
        "name": "晴",
        "weight": 28,
        "line": "晨光晒过被褥，窗格亮得像刚擦过。",
    },
    {
        "id": "rain",
        "name": "雨",
        "weight": 24,
        "line": "雨点沿檐口排队，旅人进门时会先看温泉。",
    },
    {
        "id": "wind",
        "name": "风",
        "weight": 18,
        "line": "山风把门帘吹得发响，今天更容易冒出小抱怨。",
    },
    {
        "id": "fog",
        "name": "雾",
        "weight": 16,
        "line": "雾气从坡下漫上来，远处的声音会晚一点抵达。",
    },
    {
        "id": "snow",
        "name": "雪",
        "weight": 8,
        "line": "细雪落在屋脊上，热汤和柴火都会显得更重要。",
    },
]

_GUEST_TYPES = [
    {
        "id": "bookkeeper",
        "title": "赶账的职员",
        "pay": 16,
        "bath": 0,
        "patience": 2,
        "weight": 18,
        "codex": "late_receipt",
        "wish": "要一张安静的桌角。",
    },
    {
        "id": "letter_carrier",
        "title": "邮路上的客人",
        "pay": 14,
        "bath": 1,
        "patience": 2,
        "weight": 16,
        "codex": "warm_stamp",
        "wish": "把湿邮袋放在炉边。",
    },
    {
        "id": "retired_teacher",
        "title": "退休教师",
        "pay": 17,
        "bath": 0,
        "patience": 3,
        "weight": 15,
        "codex": "chalk_note",
        "wish": "晚饭后想借一盏灯。",
    },
    {
        "id": "station_pianist",
        "title": "车站琴师",
        "pay": 18,
        "bath": 1,
        "patience": 1,
        "weight": 12,
        "codex": "soft_key",
        "wish": "行李里有一叠旧谱。",
    },
    {
        "id": "map_mender",
        "title": "修地图的人",
        "pay": 15,
        "bath": 0,
        "patience": 2,
        "weight": 12,
        "codex": "folded_map",
        "wish": "总在问窗外那条小路。",
    },
    {
        "id": "night_nurse",
        "title": "夜班归来的护士",
        "pay": 19,
        "bath": 1,
        "patience": 3,
        "weight": 10,
        "codex": "quiet_alarm",
        "wish": "希望这一晚没有急促的铃声。",
    },
    {
        "id": "apprentice_cook",
        "title": "学徒厨师",
        "pay": 13,
        "bath": 0,
        "patience": 2,
        "weight": 14,
        "codex": "borrowed_recipe",
        "wish": "闻到汤锅就会停下脚步。",
    },
    {
        "id": "calendar_seller",
        "title": "卖旧日历的人",
        "pay": 12,
        "bath": 1,
        "patience": 1,
        "weight": 9,
        "codex": "wrong_date",
        "wish": "每页都夹着不同年份的车票。",
    },
    {
        "id": "umbrella_mender",
        "title": "修伞匠",
        "pay": 14,
        "bath": 0,
        "patience": 2,
        "weight": 11,
        "codex": "patched_umbrella",
        "wish": "想找一处能慢慢晾开伞骨的角落。",
    },
    {
        "id": "botanist",
        "title": "采叶的植物学徒",
        "pay": 15,
        "bath": 0,
        "patience": 3,
        "weight": 10,
        "codex": "pressed_leaf",
        "wish": "问庭院里有没有不会被踩到的苔藓。",
    },
    {
        "id": "film_projectionist",
        "title": "巡回放映员",
        "pay": 18,
        "bath": 1,
        "patience": 2,
        "weight": 8,
        "codex": "silver_ticket",
        "wish": "箱子里有一卷怕潮的旧胶片。",
    },
    {
        "id": "sleepless_poet",
        "title": "失眠的俳句客",
        "pay": 13,
        "bath": 1,
        "patience": 1,
        "weight": 9,
        "codex": "blank_haiku",
        "wish": "说自己只需要一夜听得见水声的安静。",
    },
    {
        "id": "bath_scholar",
        "title": "温泉研究者",
        "pay": 20,
        "bath": 1,
        "patience": 2,
        "weight": 7,
        "codex": "mineral_note",
        "wish": "带着小瓶子，想比较泉水的温度。",
    },
    {
        "id": "mountain_ranger",
        "title": "巡山员",
        "pay": 16,
        "bath": 0,
        "patience": 3,
        "weight": 9,
        "codex": "pine_whistle",
        "wish": "靴底有松针，进门先看柴棚。",
    },
]

_GUEST_PREFIX = ["沈", "林", "白", "陆", "江", "许", "闻", "乔", "夏", "程"]
_GUEST_SUFFIX = ["灯", "岚", "舟", "遥", "青", "序", "棠", "禾", "眠", "川"]

_GUEST_TRAITS = [
    {
        "id": "quiet",
        "name": "喜静",
        "line": "听见走廊安静会放松。",
        "weight": 14,
        "room": 1,
        "complaint": -4,
    },
    {
        "id": "hungry",
        "name": "赶路饿了",
        "line": "眼神一直飘向厨房。",
        "weight": 13,
        "meal": 1,
    },
    {
        "id": "cold",
        "name": "怕冷",
        "line": "进门先搓手。",
        "weight": 12,
        "bath": 1,
        "bath_want": 35,
        "complaint": 5,
    },
    {
        "id": "chatty",
        "name": "爱聊天",
        "line": "愿意在前厅多坐一会儿。",
        "weight": 11,
        "greet": 1,
    },
    {
        "id": "tidy",
        "name": "爱整洁",
        "line": "会留意被角和窗台。",
        "weight": 10,
        "clean": 1,
        "complaint": 4,
    },
    {
        "id": "nostalgic",
        "name": "恋旧",
        "line": "对旧摆件特别上心。",
        "weight": 9,
        "memory": 1,
    },
    {
        "id": "light_sleeper",
        "name": "浅眠",
        "line": "风声会让人皱眉。",
        "weight": 9,
        "complaint": 2,
        "wind_complaint": 10,
    },
    {
        "id": "soak",
        "name": "爱热汤",
        "line": "把毛巾叠得很认真。",
        "weight": 8,
        "bath": 1,
        "bath_want": 28,
    },
    {
        "id": "thrifty",
        "name": "会算账",
        "line": "对小费克制，但会认真记人情。",
        "weight": 7,
        "tip": -1,
        "memory": 1,
    },
]

_CODEX = {
    "first_bell": {
        "title": "第一声柜铃",
        "text": "旅馆重新开张时，铃声比账本先记住了这一天。",
    },
    "late_receipt": {
        "title": "迟到的收据",
        "text": "有人把一张收据折进书页里，金额旁边写着天气。",
    },
    "warm_stamp": {
        "title": "温热的邮票",
        "text": "湿邮袋烤干后，邮票背面留下淡淡的汤锅味。",
    },
    "chalk_note": {
        "title": "粉笔边注",
        "text": "旧练习本上有一句评语：这家旅馆会认真听人说完。",
    },
    "soft_key": {
        "title": "很轻的琴键",
        "text": "琴师离店时，柜台上多了一枚不会发声的白键。",
    },
    "folded_map": {
        "title": "折错的地图",
        "text": "地图有一处折痕指向后院，像是路线自己改了主意。",
    },
    "quiet_alarm": {
        "title": "安静的闹钟",
        "text": "闹钟没有响，但有人在清晨醒来时终于睡够了。",
    },
    "borrowed_recipe": {
        "title": "借来的菜谱",
        "text": "菜谱末页写着：好吃不难，难的是记住谁怕烫。",
    },
    "wrong_date": {
        "title": "日期不对的票根",
        "text": "票根上的年份已经过去很久，可客人说那天还没到。",
    },
    "garden_lamp": {
        "title": "石灯下的便条",
        "text": "庭院石灯里压着一张便条，只写了房号，没有姓名。",
    },
    "fog_window": {
        "title": "雾里的窗",
        "text": "雾天擦窗时，玻璃另一侧短暂映出一间从未建过的客房。",
    },
    "rain_roof": {
        "title": "檐雨的节拍",
        "text": "雨夜的檐声敲出一段稳定节拍，客人们不再急着说话。",
    },
    "snow_kettle": {
        "title": "雪夜水壶",
        "text": "水壶在雪夜响了三次，第三次像是在替谁道谢。",
    },
    "old_key": {
        "title": "无牌旧钥匙",
        "text": "抽屉最深处的钥匙没有房号，却能打开一段谈话。",
    },
    "shop_stamp": {
        "title": "杂货店印章",
        "text": "老板把印章盖在账页角落，说旅馆也需要一点街坊气。",
    },
    "patched_umbrella": {
        "title": "补过三次的伞",
        "text": "伞面有三种线色，像不同雨天互相认出了对方。",
    },
    "pressed_leaf": {
        "title": "夹在账本里的叶",
        "text": "叶脉干净得像一张小地图，标着庭院最少有人打扰的地方。",
    },
    "silver_ticket": {
        "title": "银边电影票",
        "text": "票根背面写着片名，墨迹被温泉水汽晕开了一点。",
    },
    "blank_haiku": {
        "title": "空白俳句",
        "text": "纸上没有字，只有一个被水声留出来的停顿。",
    },
    "mineral_note": {
        "title": "矿物温度笔记",
        "text": "研究者量了三遍泉水，最后把“合适”写成了“被照顾”。",
    },
    "pine_whistle": {
        "title": "松针哨",
        "text": "巡山员教你吹响一片松针，声音短得像山路拐弯。",
    },
    "pantry_song": {
        "title": "米缸里的小调",
        "text": "夜里米缸轻轻响过，第二天盛饭的人都下意识放慢了手。",
    },
    "mirror_steam": {
        "title": "镜中水汽",
        "text": "温泉镜面雾开时，多映出一盏还没有挂上的灯。",
    },
    "lost_button": {
        "title": "不知谁的扣子",
        "text": "扣子被缝进备用枕套，后来每个枕头都像更懂告别。",
    },
    "moon_guest": {
        "title": "月下未署名",
        "text": "有人在夜里没有登记，只把一枚月白色房牌放回柜台。",
    },
}
_CODEX_ORDER = list(_CODEX.keys())

_UPGRADES = {
    "rooms": {
        "name": "客房",
        "aliases": ["客房", "房间", "rooms", "room"],
        "base": 42,
        "max": 3,
        "effect": "多一间可安排的房，打扫更有价值。",
    },
    "kitchen": {
        "name": "厨房",
        "aliases": ["厨房", "灶间", "kitchen", "cook"],
        "base": 38,
        "max": 3,
        "effect": "餐食更稳，做饭偶尔省食材。",
    },
    "onsen": {
        "name": "温泉",
        "aliases": ["温泉", "汤屋", "onsen", "spa", "bath"],
        "base": 40,
        "max": 3,
        "effect": "泡汤更能留下好心情。",
    },
    "garden": {
        "name": "庭院",
        "aliases": ["庭院", "院子", "garden", "yard"],
        "base": 32,
        "max": 3,
        "effect": "庭院行动更容易发现记忆。",
    },
    "sign": {
        "name": "招牌",
        "aliases": ["招牌", "门牌", "sign"],
        "base": 36,
        "max": 3,
        "effect": "更多客人会找到这里。",
    },
}
_UPGRADE_ALIASES = {
    alias: key for key, spec in _UPGRADES.items() for alias in spec["aliases"]
}

_DAY_EVENTS = [
    {
        "id": "market_cart",
        "title": "早市菜车",
        "line": "早市菜车绕到门口，老板多塞了两份当季食材。食材+2。",
        "weight": 12,
        "weather": None,
        "effects": {"food": 2},
    },
    {
        "id": "woodcutter_gift",
        "title": "柴棚问候",
        "line": "巡山的熟人把两捆干柴靠在柴棚边，说路过顺手。柴火+2。",
        "weight": 10,
        "weather": None,
        "effects": {"wood": 2},
    },
    {
        "id": "festival_drums",
        "title": "坡下小祭",
        "line": "坡下办小祭，更多人会经过旅馆，但鼓声也容易惹出小抱怨。",
        "weight": 9,
        "weather": None,
        "guest_delta": 1,
        "complaint": 8,
    },
    {
        "id": "muddy_road",
        "title": "山路泥泞",
        "line": "山路泥泞，客流少一点，进门的人却更想泡热汤。",
        "weight": 9,
        "weather": "rain",
        "guest_delta": -1,
        "bath_want": 25,
        "complaint": 5,
    },
    {
        "id": "spring_warm",
        "title": "泉眼升温",
        "line": "泉眼今天格外温热，温泉每次少耗一捆柴。",
        "weight": 8,
        "weather": None,
        "bath_wood": -1,
    },
    {
        "id": "quiet_hour",
        "title": "午后静时",
        "line": "午后忽然安静，今天认真处理客诉会额外安抚人心。",
        "weight": 8,
        "weather": None,
        "complaint_mood": 1,
    },
    {
        "id": "price_rumor",
        "title": "街价浮动",
        "line": "街上说今日杂货便宜，商店食材和柴火各少一钱。",
        "weight": 7,
        "weather": None,
        "shop_discount": 1,
    },
    {
        "id": "linen_delay",
        "title": "晾布未干",
        "line": "昨夜湿气重，几条床单没干。今天安排客房更需要耐心。",
        "weight": 7,
        "weather": "fog",
        "room_mood": -1,
        "complaint": 4,
    },
    {
        "id": "clear_stars",
        "title": "星光很近",
        "line": "晴夜后的星光像还没收走，今天恋旧的客人更容易留下记忆。",
        "weight": 6,
        "weather": "sun",
        "memory_bonus": 1,
    },
    {
        "id": "spring_buds",
        "title": "春芽入篮",
        "line": "庭院新芽可以入汤，你剪下一小把，食材+1，记忆+1。",
        "weight": 8,
        "season": "spring",
        "effects": {"food": 1, "memory": 1},
    },
    {
        "id": "summer_fireflies",
        "title": "夏夜萤光",
        "line": "昨夜有萤光停在竹帘外，今天招呼客人更容易聊到往事。",
        "weight": 7,
        "season": "summer",
        "memory_bonus": 1,
        "complaint_mood": 1,
    },
    {
        "id": "autumn_chestnuts",
        "title": "秋栗落地",
        "line": "院里落了几颗栗子，厨房多出一份能让人慢下来的甜味。食材+1。",
        "weight": 8,
        "season": "autumn",
        "effects": {"food": 1},
        "meal_mood": 1,
    },
    {
        "id": "winter_tracks",
        "title": "冬日足迹",
        "line": "雪地足迹绕过柴棚，像提醒你今日柴火要更仔细。拾柴额外+1。",
        "weight": 8,
        "season": "winter",
        "wood_gain": 1,
    },
]

_RARE_EVENTS = [
    {
        "id": "garden_lamp",
        "title": "石灯亮了一下",
        "line": "你经过庭院时，石灯自己亮了一下，里面压着一张干净便条。",
        "weather": None,
        "triggers": ["garden"],
        "bonus": {"memory": 3},
    },
    {
        "id": "fog_window",
        "title": "多出来的窗影",
        "line": "雾贴着玻璃，你擦到第三遍时，看见一扇不属于这栋楼的窗。",
        "weather": "fog",
        "triggers": ["rooms", "front", "night"],
        "bonus": {"memory": 4},
    },
    {
        "id": "rain_roof",
        "title": "檐声合拍",
        "line": "雨声忽然变得整齐，前厅里的人都安静听完了那一小段。",
        "weather": "rain",
        "triggers": ["front", "night"],
        "bonus": {"memory": 4},
    },
    {
        "id": "snow_kettle",
        "title": "水壶三响",
        "line": "雪夜水壶响了三次，第三次之后，柴火像是更耐烧了。",
        "weather": "snow",
        "triggers": ["kitchen", "night"],
        "bonus": {"memory": 4, "wood": 1},
    },
    {
        "id": "old_key",
        "title": "旧钥匙开口",
        "line": "抽屉里那枚旧钥匙碰到柜台，声音轻得像有人说了一句谢谢。",
        "weather": None,
        "triggers": ["front", "rooms", "night"],
        "bonus": {"memory": 3, "money": 2},
    },
    {
        "id": "pantry_song",
        "title": "米缸里的小调",
        "line": "厨房米缸轻轻响起一段小调，你盛饭时忽然知道该少急一点。",
        "weather": None,
        "triggers": ["kitchen"],
        "bonus": {"memory": 3, "food": 1},
    },
    {
        "id": "mirror_steam",
        "title": "镜中多灯",
        "line": "温泉镜面被水汽擦开一角，里面多映出一盏还没挂上的灯。",
        "weather": None,
        "triggers": ["onsen"],
        "bonus": {"memory": 4},
    },
    {
        "id": "lost_button",
        "title": "枕套里的扣子",
        "line": "打扫时，你从备用枕套里摸出一枚不知谁留下的扣子。",
        "weather": None,
        "triggers": ["rooms"],
        "bonus": {"memory": 3},
    },
    {
        "id": "moon_guest",
        "title": "月下房牌",
        "line": "夜里柜台多出一枚月白色房牌，登记簿上却没有新名字。",
        "weather": None,
        "triggers": ["night"],
        "bonus": {"memory": 5, "money": 1},
    },
]

_HELP_TEXT = (
    "可说：去 前厅/客房/厨房/温泉/庭院/商店；客人；安排 全部；"
    + "做饭 1；温泉 全部；客诉 全部；备料；拾柴；打扫；招呼；"
    + "买 食材 3；升级 厨房；图鉴；状态；年度总结；结束一天。"
    + "可用分号、换行或“然后”输入批量指令。"
)


def new_game(seed: Any = _DEFAULT_SEED) -> str:
    """Start a deterministic new game and save it."""
    global _GAME
    game = _fresh_game(seed)
    lines = [
        "雾灯旅馆重新开门。你把钥匙牌排齐，决定让这里先记住人，再记住账。",
        _unlock(game, "first_bell"),
        _start_day(game),
        "输入“帮助”可看不剧透的指令表。",
    ]
    _GAME = game
    _save(game)
    return _finish(lines, game)


def cmd(text: Any) -> str:
    """Run one or more text commands against the current save."""
    global _GAME
    if _GAME is None:
        _GAME = _load() or _fresh_game(_DEFAULT_SEED)
        if _GAME["day"] == 0:
            _start_day(_GAME)
    game = _GAME
    parts = _split_commands(str(text))
    if not parts:
        parts = ["状态"]
    lines: list[str] = []
    for index, part in enumerate(parts, start=1):
        result = _handle_command(game, part)
        if len(parts) > 1:
            lines.append("[{}] {}".format(index, result))
        else:
            lines.append(result)
    _save(game)
    return _finish(lines, game)


def _fresh_game(seed: Any) -> dict[str, Any]:
    seed_text = str(seed)
    return {
        "version": _VERSION,
        "seed": seed_text,
        "rng": _seed_to_int(seed_text),
        "day": 0,
        "location": "front",
        "weather": "sun",
        "money": 44,
        "food": 7,
        "wood": 6,
        "energy": 6,
        "max_energy": 6,
        "clock": 0,
        "memory": 0,
        "served": 0,
        "guest_seq": 0,
        "guests": [],
        "today_event": "",
        "annual": _new_annual_stats(),
        "year_reports": [],
        "codex": [],
        "upgrades": {"rooms": 0, "kitchen": 0, "onsen": 0, "garden": 0, "sign": 0},
        "flags": {"ending_seen": False},
    }


def _save_path() -> str:
    return os.environ.get(
        "HOTEL_GAME_SAVE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), _SAVE_NAME),
    )


def _save(game: dict[str, Any]) -> None:
    path = _save_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {"version": _VERSION, "game": game}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load() -> dict[str, Any] | None:
    path = _save_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != _VERSION:
        return None
    game = payload.get("game")
    if not isinstance(game, dict):
        return None
    return _migrate(game)


def _migrate(game: dict[str, Any]) -> dict[str, Any]:
    game.setdefault("version", _VERSION)
    game.setdefault("codex", [])
    game.setdefault("guests", [])
    game.setdefault("today_event", "")
    game.setdefault("clock", 0)
    game.setdefault("year_reports", [])
    _annual(game)
    game.setdefault("flags", {})
    game.setdefault("upgrades", {"rooms": 0, "kitchen": 0, "onsen": 0, "garden": 0, "sign": 0})
    for key in _UPGRADES:
        game["upgrades"].setdefault(key, 0)
    return game


def _seed_to_int(seed_text: str) -> int:
    value = 2166136261
    for char in seed_text:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    if value == 0:
        value = 2463534242
    return value


def _rand(game: dict[str, Any]) -> int:
    x = int(game["rng"]) & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    game["rng"] = x & 0xFFFFFFFF
    return int(game["rng"])


def _randrange(game: dict[str, Any], limit: int) -> int:
    if limit <= 0:
        return 0
    return _rand(game) % limit


def _chance(game: dict[str, Any], percent: int) -> bool:
    percent = max(0, min(100, percent))
    return _randrange(game, 100) < percent


def _weighted_choice(game: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(max(0, int(item.get("weight", 1))) for item in items)
    pick = _randrange(game, total)
    running = 0
    for item in items:
        running += max(0, int(item.get("weight", 1)))
        if pick < running:
            return item
    return items[-1]


def _new_annual_stats() -> dict[str, Any]:
    return {
        "days": 0,
        "guests": 0,
        "served": 0,
        "income": 0,
        "spent": 0,
        "memory": 0,
        "codex": 0,
        "rare_events": 0,
        "missed_rooms": 0,
        "missed_meals": 0,
        "missed_baths": 0,
        "unresolved_complaints": 0,
        "food_gained": 0,
        "wood_gained": 0,
        "wood_used": 0,
        "actions": {
            "rooms": 0,
            "meals": 0,
            "baths": 0,
            "complaints": 0,
            "prep": 0,
            "wood": 0,
            "clean": 0,
            "greet": 0,
            "buys": 0,
            "upgrades": 0,
            "garden_visits": 0,
        },
        "season_days": {"spring": 0, "summer": 0, "autumn": 0, "winter": 0},
    }


def _annual(game: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(game.get("annual"), dict):
        game["annual"] = _new_annual_stats()
    stats = game["annual"]
    defaults = _new_annual_stats()
    for key, value in defaults.items():
        if isinstance(value, dict):
            stats.setdefault(key, {})
            for sub_key, sub_value in value.items():
                stats[key].setdefault(sub_key, sub_value)
        else:
            stats.setdefault(key, value)
    return stats


def _record_action(game: dict[str, Any], key: str, amount: int = 1) -> None:
    stats = _annual(game)
    stats["actions"][key] = int(stats["actions"].get(key, 0)) + amount


def _year_for_day(day: int) -> int:
    return max(1, (max(1, day) - 1) // _DAYS_PER_YEAR + 1)


def _day_of_year(day: int) -> int:
    return (max(1, day) - 1) % _DAYS_PER_YEAR + 1


def _day_of_season(day: int) -> int:
    return (_day_of_year(day) - 1) % _DAYS_PER_SEASON + 1


def _season_for_day(day: int) -> dict[str, Any]:
    index = (_day_of_year(day) - 1) // _DAYS_PER_SEASON
    return _SEASONS[index]


def _season(game: dict[str, Any]) -> dict[str, Any]:
    return _season_for_day(int(game.get("day", 1)))


def _date_text(day: int) -> str:
    season = _season_for_day(day)
    return "第{}年{}第{}天".format(
        _year_for_day(day),
        season["name"],
        _day_of_season(day),
    )


def _weather_options(day: int) -> list[dict[str, Any]]:
    weights = _season_for_day(day)["weather"]
    options = []
    for weather in _WEATHERS:
        option = dict(weather)
        option["weight"] = int(weights.get(weather["id"], weather["weight"]))
        options.append(option)
    return options


def _time_label(game: dict[str, Any]) -> str:
    index = max(0, min(len(_TIME_SLOTS) - 1, int(game.get("clock", 0))))
    return _TIME_SLOTS[index]


def _advance_time(game: dict[str, Any], steps: int = 1) -> None:
    game["clock"] = max(0, min(len(_TIME_SLOTS) - 1, int(game.get("clock", 0)) + steps))


def _spend_energy(game: dict[str, Any], amount: int = 1) -> None:
    game["energy"] = max(0, int(game["energy"]) - amount)
    _advance_time(game, amount)


def _stable_pick(game: dict[str, Any], salt: str, values: list[str]) -> str:
    if not values:
        return ""
    base = "{}:{}:{}:{}".format(game.get("seed", ""), game.get("day", 0), game.get("clock", 0), salt)
    return values[_seed_to_int(base) % len(values)]


def _garden_scene(game: dict[str, Any]) -> str:
    season = _season(game)
    plant = _stable_pick(game, "plant", season["plants"])
    animal = _stable_pick(game, "animal", season["animals"])
    level = int(game["upgrades"].get("garden", 0))
    extra = ""
    if level >= 2:
        extra = "升级过的石径让它们不太怕人。"
    elif level >= 1:
        extra = "修过的篱笆让风声柔和一点。"
    return "庭院是{}景：{}贴着石灯，{}在附近停留。{}".format(
        season["name"],
        plant,
        animal,
        extra,
    )


def _start_day(game: dict[str, Any]) -> str:
    game["day"] += 1
    season = _season(game)
    weather = _weighted_choice(game, _weather_options(game["day"]))
    game["weather"] = weather["id"]
    game["today_event"] = ""
    game["clock"] = 0
    game["max_energy"] = 6 + min(2, int(game["upgrades"]["garden"]))
    game["energy"] = game["max_energy"]
    game["location"] = "front"
    event_line = _roll_day_event(game)
    game["guests"] = _make_guests(game)
    stats = _annual(game)
    stats["days"] += 1
    stats["guests"] += len(game["guests"])
    stats["season_days"][season["id"]] += 1
    lines = [
        "{}，{}，天气：{}。{}".format(_date_text(game["day"]), _time_label(game), weather["name"], weather["line"]),
        "今天来了{}位客人。先看“客人”，再决定房间、餐食、温泉和客诉。".format(len(game["guests"])),
    ]
    if _day_of_season(game["day"]) == 1:
        lines.insert(1, "换季：{}{}".format(season["start"], _garden_scene(game)))
    if event_line:
        lines.insert(1, event_line)
    if game["day"] == 14:
        lines.append("账本夹层露出一行字：明天以后，旅馆会按记忆而不是金额评价你。")
    return "\n".join(lines)


def _roll_day_event(game: dict[str, Any]) -> str:
    chance = 42 + min(12, int(game["upgrades"]["sign"]) * 3)
    if not _chance(game, chance):
        return ""
    season_id = _season(game)["id"]
    possible = [
        event
        for event in _DAY_EVENTS
        if event.get("weather") is None or event.get("weather") == game["weather"]
        if event.get("season") is None or event.get("season") == season_id
    ]
    if not possible:
        return ""
    event = _weighted_choice(game, possible)
    game["today_event"] = event["id"]
    for key, value in event.get("effects", {}).items():
        game[key] = game.get(key, 0) + value
        if key == "memory":
            _annual(game)["memory"] += value
    return "今日小事：{}。{}".format(event["title"], event["line"])


def _make_guests(game: dict[str, Any]) -> list[dict[str, Any]]:
    room_cap = _room_capacity(game)
    sign = int(game["upgrades"]["sign"])
    count = 2
    if game["day"] % 3 == 0:
        count += 1
    if sign and _chance(game, 35 + sign * 10):
        count += 1
    if game["weather"] == "snow":
        count = max(1, count - 1)
    count += int(_event_value(game, "guest_delta", 0))
    count = max(1, count)
    count = min(count, room_cap + 2)
    guests = []
    for _ in range(count):
        spec = _weighted_choice(game, _GUEST_TYPES)
        trait = _weighted_choice(game, _GUEST_TRAITS)
        game["guest_seq"] += 1
        name = "{}{}".format(
            _GUEST_PREFIX[_randrange(game, len(_GUEST_PREFIX))],
            _GUEST_SUFFIX[_randrange(game, len(_GUEST_SUFFIX))],
        )
        wants_bath = bool(spec["bath"])
        if game["weather"] in ("rain", "snow") and _chance(game, 45):
            wants_bath = True
        if int(trait.get("bath_want", 0)) and _chance(game, int(trait.get("bath_want", 0))):
            wants_bath = True
        if int(_event_value(game, "bath_want", 0)) and _chance(game, int(_event_value(game, "bath_want", 0))):
            wants_bath = True
        complaint_chance = 10 + (16 if game["weather"] == "wind" else 0)
        complaint_chance -= int(game["upgrades"]["rooms"]) * 2
        complaint_chance += int(trait.get("complaint", 0))
        if game["weather"] == "wind":
            complaint_chance += int(trait.get("wind_complaint", 0))
        complaint_chance += int(_event_value(game, "complaint", 0))
        complaint = _chance(game, complaint_chance)
        guests.append(
            {
                "id": "g{}".format(game["guest_seq"]),
                "name": name,
                "type": spec["id"],
                "title": spec["title"],
                "trait": trait["id"],
                "pay": spec["pay"],
                "patience": spec["patience"],
                "wish": spec["wish"],
                "codex": spec["codex"],
                "wants_bath": wants_bath,
                "room": False,
                "meal": False,
                "bath": False,
                "complaint": complaint,
                "mood": 0,
                "note": "",
            }
        )
    return guests


def _room_capacity(game: dict[str, Any]) -> int:
    return 2 + int(game["upgrades"]["rooms"])


def _room_used(game: dict[str, Any]) -> int:
    return sum(1 for guest in game["guests"] if guest["room"])


def _finish(lines: list[str], game: dict[str, Any]) -> str:
    clean_lines = [line for line in lines if line]
    clean_lines.append(_status_line(game))
    return "\n".join(clean_lines)


def _status_line(game: dict[str, Any]) -> str:
    todo = {
        "room": sum(1 for guest in game["guests"] if not guest["room"]),
        "meal": sum(1 for guest in game["guests"] if not guest["meal"]),
        "bath": sum(1 for guest in game["guests"] if guest["wants_bath"] and not guest["bath"]),
        "complaint": sum(1 for guest in game["guests"] if guest["complaint"]),
    }
    status = {
        "day": game["day"],
        "year": _year_for_day(game["day"]),
        "season": _season(game)["name"],
        "doy": _day_of_year(game["day"]),
        "time": _time_label(game),
        "loc": _loc_name(game["location"]),
        "weather": _weather(game)["name"],
        "event": _today_event(game)["title"] if _today_event(game) else "",
        "money": game["money"],
        "food": game["food"],
        "wood": game["wood"],
        "energy": game["energy"],
        "guests": len(game["guests"]),
        "todo": todo,
        "memory": game["memory"],
        "codex": len(game["codex"]),
        "saved": True,
    }
    return json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _split_commands(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("；", ";").replace("\n", ";")
    text = text.replace("然后", ";").replace("再然后", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def _handle_command(game: dict[str, Any], raw: str) -> str:
    text = _norm(raw)
    if not text:
        return _brief_status(game)
    if _has(text, ["帮助", "help", "?"]):
        return _HELP_TEXT
    if _has(text, ["状态", "账本", "旅馆", "status", "look"]):
        return _brief_status(game)
    if _starts_move(text):
        return _move(game, text)
    if _has(text, ["客人", "名单", "住客", "guest", "guests", "list"]):
        return _guest_list(game)
    if _has(text, ["图鉴", "记忆", "memory", "codex", "album"]):
        return _show_codex(game)
    if _has(text, ["年度", "年报", "年终", "性格画像", "性格"]):
        return _annual_preview(game)
    if _has(text, ["商店", "价目", "shop", "market"]) and not _has(text, ["买", "buy", "升级", "upgrade"]):
        return _shop(game)
    if _has(text, ["买", "购买", "buy"]):
        return _buy(game, text)
    if _has(text, ["升级", "upgrade"]):
        return _upgrade(game, text)
    if _has(text, ["结束", "过夜", "睡觉", "明天", "下一天", "end", "night"]):
        return _end_day(game)
    if _has(text, ["安排", "开房", "入住", "房间", "room", "checkin"]):
        return _assign_rooms(game, text)
    if _has(text, ["做饭", "餐食", "晚饭", "早餐", "吃饭", "meal", "cook", "feed"]):
        return _serve_meals(game, text)
    if _has(text, ["泡汤", "温泉", "汤屋", "bath", "spa", "onsen"]):
        return _serve_bath(game, text)
    if _has(text, ["客诉", "投诉", "安抚", "道歉", "complaint", "soothe"]):
        return _handle_complaints(game, text)
    if _has(text, ["备料", "采购", "买菜", "食材", "forage", "prep"]):
        return _prep_food(game)
    if _has(text, ["拾柴", "劈柴", "柴火", "wood", "chop"]):
        return _gather_wood(game)
    if _has(text, ["打扫", "清扫", "clean"]):
        return _clean_rooms(game)
    if _has(text, ["招呼", "寒暄", "聊天", "greet", "talk"]):
        return _greet(game)
    if _has(text, ["保存", "save"]):
        _save(game)
        return "已经自动保存。"
    return "你记下这句：“{}”。它还不是旅馆听得懂的指令。输入“帮助”可看指令。".format(raw.strip())


def _norm(text: str) -> str:
    return text.strip().lower()


def _has(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _starts_move(text: str) -> bool:
    if text in _LOCATION_ALIASES:
        return True
    return text.startswith(("去", "到", "前往", "移动", "goto ", "go "))


def _move(game: dict[str, Any], text: str) -> str:
    target = _find_location(text)
    if target is None:
        return "可去：{}。".format("、".join(_loc_name(key) for key in _LOCATIONS))
    game["location"] = target
    if target == "garden":
        _record_action(game, "garden_visits")
        return "你来到{}。{}\n{}".format(_loc_name(target), _LOCATIONS[target]["look"], _garden_scene(game))
    return "你来到{}。{}".format(_loc_name(target), _LOCATIONS[target]["look"])


def _find_location(text: str) -> str | None:
    for alias, key in sorted(_LOCATION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in text:
            return key
    return None


def _loc_name(key: str) -> str:
    return _LOCATIONS.get(key, _LOCATIONS["front"])["name"]


def _weather(game: dict[str, Any]) -> dict[str, Any]:
    for weather in _WEATHERS:
        if weather["id"] == game["weather"]:
            return weather
    return _WEATHERS[0]


def _today_event(game: dict[str, Any]) -> dict[str, Any] | None:
    event_id = game.get("today_event", "")
    for event in _DAY_EVENTS:
        if event["id"] == event_id:
            return event
    return None


def _event_value(game: dict[str, Any], key: str, default: int = 0) -> int:
    event = _today_event(game)
    if event is None:
        return default
    return int(event.get(key, default))


def _trait(guest: dict[str, Any]) -> dict[str, Any]:
    trait_id = guest.get("trait", "")
    for trait in _GUEST_TRAITS:
        if trait["id"] == trait_id:
            return trait
    return _GUEST_TRAITS[0]


def _brief_status(game: dict[str, Any]) -> str:
    event = _today_event(game)
    event_text = "，今日小事：{}".format(event["title"]) if event else ""
    return (
        (
            "{}，{}，{}{}，你在{}。钱{}，食材{}，柴火{}，体力{}/{}，客人{}位，"
            + "房间{}/{}，记忆{}，图鉴{}。"
        ).format(
            _date_text(game["day"]),
            _time_label(game),
            _weather(game)["name"],
            event_text,
            _loc_name(game["location"]),
            game["money"],
            game["food"],
            game["wood"],
            game["energy"],
            game["max_energy"],
            len(game["guests"]),
            _room_used(game),
            _room_capacity(game),
            game["memory"],
            len(game["codex"]),
        )
    )


def _guest_list(game: dict[str, Any]) -> str:
    if not game["guests"]:
        return "今天没有住客，柜铃安静得像一枚纽扣。"
    lines = ["今日住客："]
    for idx, guest in enumerate(game["guests"], start=1):
        trait = _trait(guest)
        marks = [
            "房{}".format("✓" if guest["room"] else "×"),
            "饭{}".format("✓" if guest["meal"] else "×"),
        ]
        if guest["wants_bath"]:
            marks.append("汤{}".format("✓" if guest["bath"] else "×"))
        if guest["complaint"]:
            marks.append("客诉!")
        mood = "心情{:+d}".format(int(guest["mood"]))
        lines.append(
            "{}. {}（{}，{}）{}；{}；愿望：{}；性格：{}".format(
                idx,
                guest["name"],
                guest["title"],
                trait["name"],
                "、".join(marks),
                mood,
                guest["wish"],
                trait["line"],
            )
        )
    return "\n".join(lines)


def _show_codex(game: dict[str, Any]) -> str:
    if not game["codex"]:
        return "图鉴还是空的。记忆不会急，它通常藏在照顾人的细节里。"
    lines = ["已收集的旅馆记忆（{}）：".format(len(game["codex"]))]
    for key in _CODEX_ORDER:
        if key in game["codex"]:
            entry = _CODEX[key]
            lines.append("- {}：{}".format(entry["title"], entry["text"]))
    return "\n".join(lines)


def _shop(game: dict[str, Any]) -> str:
    food_price = _shop_price(game, "food")
    wood_price = _shop_price(game, "wood")
    lines = [
        "商店价目：食材{}钱/份，柴火{}钱/捆。".format(food_price, wood_price),
        "升级：{}".format(
            "；".join(
                "{}{}级→{}钱".format(
                    spec["name"],
                    game["upgrades"][key],
                    _upgrade_cost(game, key),
                )
                if game["upgrades"][key] < spec["max"]
                else "{}已满级".format(spec["name"])
                for key, spec in _UPGRADES.items()
            )
        ),
        "例：买 食材 3；升级 客房。",
    ]
    return "\n".join(lines)


def _shop_price(game: dict[str, Any], item: str) -> int:
    base = 4 if item == "food" else 3
    return max(1, base - int(_event_value(game, "shop_discount", 0)))


def _buy(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "shop")
    if need:
        return need
    amount = _first_number(text, 1)
    amount = max(1, min(20, amount))
    if _has(text, ["食材", "food", "菜"]):
        cost = amount * _shop_price(game, "food")
        if game["money"] < cost:
            return "钱不够。{}份食材要{}钱。".format(amount, cost)
        game["money"] -= cost
        game["food"] += amount
        _advance_time(game)
        _record_action(game, "buys")
        _annual(game)["spent"] += cost
        extra = _unlock(game, "shop_stamp") if "shop_stamp" not in game["codex"] and amount >= 3 else ""
        return "买入{}份食材，花{}钱。{}".format(amount, cost, extra)
    if _has(text, ["柴", "wood"]):
        cost = amount * _shop_price(game, "wood")
        if game["money"] < cost:
            return "钱不够。{}捆柴火要{}钱。".format(amount, cost)
        game["money"] -= cost
        game["wood"] += amount
        _advance_time(game)
        _record_action(game, "buys")
        _annual(game)["spent"] += cost
        extra = _unlock(game, "shop_stamp") if "shop_stamp" not in game["codex"] and amount >= 3 else ""
        return "买入{}捆柴火，花{}钱。{}".format(amount, cost, extra)
    return "商店能买：食材、柴火。例：买 食材 3。"


def _upgrade(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "shop")
    if need:
        return need
    target = _find_upgrade(text)
    if target is None:
        return "可升级：{}。".format("、".join(spec["name"] for spec in _UPGRADES.values()))
    spec = _UPGRADES[target]
    level = int(game["upgrades"][target])
    if level >= spec["max"]:
        return "{}已经满级。".format(spec["name"])
    cost = _upgrade_cost(game, target)
    if game["money"] < cost:
        return "钱不够。升级{}需要{}钱。".format(spec["name"], cost)
    game["money"] -= cost
    game["upgrades"][target] = level + 1
    _advance_time(game)
    _record_action(game, "upgrades")
    _annual(game)["spent"] += cost
    if target == "garden":
        game["max_energy"] = 6 + min(2, int(game["upgrades"]["garden"]))
        game["energy"] = min(game["energy"] + 1, game["max_energy"])
    return "升级{}到{}级。{}".format(spec["name"], level + 1, spec["effect"])


def _upgrade_cost(game: dict[str, Any], key: str) -> int:
    spec = _UPGRADES[key]
    level = int(game["upgrades"][key])
    if level >= spec["max"]:
        return 0
    return int(spec["base"]) + level * 28


def _find_upgrade(text: str) -> str | None:
    for alias, key in sorted(_UPGRADE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in text:
            return key
    return None


def _need_location(game: dict[str, Any], key: str) -> str:
    if game["location"] == key:
        return ""
    return "这件事最好在{}做。你现在在{}。可先说：去 {}。".format(
        _loc_name(key),
        _loc_name(game["location"]),
        _loc_name(key),
    )


def _assign_rooms(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "rooms")
    if need:
        return need
    guests = _select_guests(game, text, lambda guest: not guest["room"])
    if not guests:
        return "没有需要安排房间的客人。"
    lines = []
    for guest in guests:
        if game["energy"] <= 0:
            lines.append("体力用尽，钥匙牌还握在手里。")
            break
        if _room_used(game) >= _room_capacity(game):
            lines.append("房间满了。剩下的人只能等你取舍。")
            break
        _spend_energy(game)
        _record_action(game, "rooms")
        guest["room"] = True
        trait = _trait(guest)
        mood = 1 + (1 if game["weather"] == "sun" else 0)
        mood += int(trait.get("room", 0)) + int(_event_value(game, "room_mood", 0))
        guest["mood"] += mood
        lines.append("给{}安排了房间，钥匙牌轻轻一响，心情{:+d}。".format(guest["name"], mood))
    return "\n".join(lines)


def _serve_meals(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "kitchen")
    if need:
        return need
    guests = _select_guests(game, text, lambda guest: not guest["meal"])
    if not guests:
        return "没有还等餐食的客人。"
    lines = []
    kitchen = int(game["upgrades"]["kitchen"])
    for guest in guests:
        if game["energy"] <= 0:
            lines.append("体力用尽，汤勺停在锅边。")
            break
        food_cost = 1
        if kitchen >= 2 and _chance(game, 25):
            food_cost = 0
        if game["food"] < food_cost:
            lines.append("食材不够。")
            break
        game["food"] -= food_cost
        _spend_energy(game)
        _record_action(game, "meals")
        guest["meal"] = True
        trait = _trait(guest)
        mood = 1 + (1 if kitchen >= 1 else 0)
        if guest["type"] == "apprentice_cook":
            mood += 1
        mood += int(trait.get("meal", 0)) + int(_event_value(game, "meal_mood", 0))
        guest["mood"] += mood
        lines.append("给{}端上餐食，心情+{}。".format(guest["name"], mood))
    return "\n".join(lines)


def _serve_bath(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "onsen")
    if need:
        return need
    guests = _select_guests(game, text, lambda guest: not guest["bath"] and guest["wants_bath"])
    if not guests:
        return "没有特别想泡温泉的客人。"
    lines = []
    onsen = int(game["upgrades"]["onsen"])
    served = 0
    for guest in guests:
        if game["energy"] <= 0:
            lines.append("体力用尽，竹帘没有再掀起。")
            break
        wood_cost = 1 + (1 if game["weather"] == "snow" and onsen == 0 else 0)
        wood_cost = max(0, wood_cost + int(_event_value(game, "bath_wood", 0)))
        if game["wood"] < wood_cost:
            lines.append("柴火不够，温泉只剩温吞水汽。")
            break
        game["wood"] -= wood_cost
        _spend_energy(game)
        _record_action(game, "baths")
        _annual(game)["wood_used"] += wood_cost
        guest["bath"] = True
        trait = _trait(guest)
        mood = 2 + (1 if onsen >= 1 else 0) + (1 if game["weather"] == "rain" else 0)
        mood += int(trait.get("bath", 0))
        guest["mood"] += mood
        served += 1
        lines.append("给{}备好温泉，耗柴{}，心情+{}。".format(guest["name"], wood_cost, mood))
    if served:
        rare = _maybe_rare(game, "onsen")
        if rare:
            lines.append(rare)
    return "\n".join(lines)


def _handle_complaints(game: dict[str, Any], text: str) -> str:
    need = _need_location(game, "front")
    if need:
        return need
    guests = _select_guests(game, text, lambda guest: guest["complaint"])
    if not guests:
        return "前厅暂时没有客诉。"
    lines = []
    for guest in guests:
        if game["energy"] <= 0:
            lines.append("体力用尽，道歉的话说到一半。")
            break
        _spend_energy(game)
        _record_action(game, "complaints")
        guest["complaint"] = False
        mood = 2 + int(game["upgrades"]["sign"] > 1) + int(_event_value(game, "complaint_mood", 0))
        guest["mood"] += mood
        lines.append("你认真听完{}的抱怨，并补上一杯热茶，心情+{}。".format(guest["name"], mood))
    return "\n".join(lines)


def _prep_food(game: dict[str, Any]) -> str:
    need = _need_location(game, "kitchen")
    if need:
        return need
    if game["energy"] <= 0:
        return "体力用尽，菜篮提不起来。"
    _spend_energy(game)
    _record_action(game, "prep")
    gain = 2 + int(game["upgrades"]["kitchen"])
    if game["weather"] == "sun":
        gain += 1
    game["food"] += gain
    _annual(game)["food_gained"] += gain
    rare = _maybe_rare(game, "kitchen")
    if rare:
        return "你备好{}份食材。厨房的台面终于有了余裕。\n{}".format(gain, rare)
    return "你备好{}份食材。厨房的台面终于有了余裕。".format(gain)


def _gather_wood(game: dict[str, Any]) -> str:
    need = _need_location(game, "garden")
    if need:
        return need
    if game["energy"] <= 0:
        return "体力用尽，柴棚看起来格外远。"
    _spend_energy(game)
    _record_action(game, "wood")
    gain = 2 + int(game["upgrades"]["garden"]) + int(_event_value(game, "wood_gain", 0))
    if game["weather"] == "wind":
        gain += 1
    game["wood"] += gain
    _annual(game)["wood_gained"] += gain
    rare = _maybe_rare(game, "garden")
    if rare:
        return "你拾回{}捆柴火。\n{}".format(gain, rare)
    return "你拾回{}捆柴火，顺手把庭院小路理清。".format(gain)


def _clean_rooms(game: dict[str, Any]) -> str:
    need = _need_location(game, "rooms")
    if need:
        return need
    if game["energy"] <= 0:
        return "体力用尽，抹布被你搭在门把上。"
    _spend_energy(game)
    _record_action(game, "clean")
    helped = 0
    extra = 0
    for guest in game["guests"]:
        if guest["room"] and not guest["complaint"]:
            mood = 1 + int(_trait(guest).get("clean", 0))
            guest["mood"] += mood
            helped += 1
            if mood > 1:
                extra += 1
    if helped == 0:
        return "你把空房打扫干净。今晚若有人入住，会少一点灰尘。"
    rare = _maybe_rare(game, "rooms")
    if rare:
        lines = [
            "你打扫了走廊和房间，{}位客人心情+1。".format(helped),
            rare,
        ]
        if extra:
            lines[0] = "你打扫了走廊和房间，{}位客人心情+1，其中{}位特别受用。".format(helped, extra)
        return "\n".join(lines)
    if extra:
        return "你打扫了走廊和房间，{}位客人心情+1，其中{}位特别受用。".format(helped, extra)
    return "你打扫了走廊和房间，{}位客人的心情各+1。".format(helped)


def _greet(game: dict[str, Any]) -> str:
    need = _need_location(game, "front")
    if need:
        return need
    if game["energy"] <= 0:
        return "体力用尽，前厅只剩柜铃陪你。"
    _spend_energy(game)
    _record_action(game, "greet")
    if not game["guests"]:
        return "你把前厅的灯调亮一点，虽然今天没有客人。"
    extra = 0
    for guest in game["guests"]:
        if not guest["complaint"]:
            mood = 1 + int(_trait(guest).get("greet", 0))
            guest["mood"] += mood
            if mood > 1:
                extra += 1
    rare = _maybe_rare(game, "front")
    base = "你在前厅招呼大家，没在抱怨的客人心情+1。"
    if extra:
        base += "{}位爱聊天的客人多坐了一会儿。".format(extra)
    if rare:
        return "{}\n{}".format(base, rare)
    return base


def _select_guests(game: dict[str, Any], text: str, predicate: Any) -> list[dict[str, Any]]:
    candidates = [guest for guest in game["guests"] if predicate(guest)]
    if not candidates:
        return []
    if _has(text, ["全部", "所有", "all", "大家"]):
        return candidates
    number = _explicit_number(text)
    if number is not None:
        index = number - 1
        if 0 <= index < len(game["guests"]):
            guest = game["guests"][index]
            return [guest] if predicate(guest) else []
    for guest in candidates:
        if guest["name"] in text or guest["title"] in text:
            return [guest]
    return [candidates[0]]


def _explicit_number(text: str) -> int | None:
    match = re.search(r"(?<!\d)(\d+)(?!\d)", text)
    if match is None:
        return None
    return int(match.group(1))


def _first_number(text: str, default: int) -> int:
    number = _explicit_number(text)
    return default if number is None else number


def _annual_preview(game: dict[str, Any]) -> str:
    stats = _annual(game)
    lines = [
        "年度观察：{}进行到第{}天，还没到年末。".format(
            _date_text(game["day"]),
            _day_of_year(game["day"]),
        ),
        _annual_numbers(stats),
        "AI性格画像：{}".format("；".join(_personality_lines(stats))),
    ]
    if game.get("year_reports"):
        last = game["year_reports"][-1]
        lines.append("最近一次完整年报：第{}年。".format(last.get("year", "?")))
    return "\n".join(lines)


def _maybe_year_summary(game: dict[str, Any]) -> str:
    if _day_of_year(game["day"]) != _DAYS_PER_YEAR:
        return ""
    stats = _annual(game)
    year = _year_for_day(game["day"])
    report = "\n".join(
        [
            "年度总结：第{}年结束。庭院走完春夏秋冬，账本把这一年夹成一页。".format(year),
            _annual_numbers(stats),
            "AI性格画像：{}".format("；".join(_personality_lines(stats))),
            _annual_garden_note(stats),
        ]
    )
    game.setdefault("year_reports", []).append({"year": year, "text": report})
    if len(game["year_reports"]) > 6:
        game["year_reports"] = game["year_reports"][-6:]
    game["annual"] = _new_annual_stats()
    return report


def _annual_numbers(stats: dict[str, Any]) -> str:
    actions = stats["actions"]
    return (
        (
            "年内记录：接待{}位，留宿{}位，收入{}钱，支出{}钱，记忆+{}，图鉴+{}；"
            + "照顾：房{}、饭{}、汤{}、客诉{}、打扫{}、招呼{}；"
            + "后勤：备料{}、拾柴{}、购物{}、升级{}；疏漏：房{}、饭{}、汤{}、客诉{}。"
        )
    ).format(
        stats["guests"],
        stats["served"],
        stats["income"],
        stats["spent"],
        stats["memory"],
        stats["codex"],
        actions["rooms"],
        actions["meals"],
        actions["baths"],
        actions["complaints"],
        actions["clean"],
        actions["greet"],
        actions["prep"],
        actions["wood"],
        actions["buys"],
        actions["upgrades"],
        stats["missed_rooms"],
        stats["missed_meals"],
        stats["missed_baths"],
        stats["unresolved_complaints"],
    )


def _personality_lines(stats: dict[str, Any]) -> list[str]:
    actions = stats["actions"]
    guests = max(1, int(stats["guests"]))
    care = actions["rooms"] + actions["meals"] + actions["baths"] + actions["complaints"] + actions["clean"] + actions["greet"]
    logistics = actions["prep"] + actions["wood"] + actions["buys"] + actions["upgrades"]
    memory = int(stats["memory"]) + int(stats["codex"]) * 2 + int(stats["rare_events"]) * 3
    garden = actions["garden_visits"] + actions["wood"]
    risk = int(stats["missed_rooms"]) + int(stats["missed_meals"]) + int(stats["missed_baths"]) + int(stats["unresolved_complaints"])
    scores = [
        ("照顾优先型", care),
        ("后勤规划型", logistics),
        ("记忆采集型", memory),
        ("庭院季节型", garden),
    ]
    scores.sort(key=lambda item: (-item[1], item[0]))
    main = scores[0][0]
    if risk >= max(3, guests // 2):
        lines = ["有压线经营倾向，常在资源、体力和客人之间冒险取舍"]
    elif scores[0][1] == 0:
        lines = ["还在试探旅馆规则，性格尚未显影"]
    elif main == "照顾优先型":
        lines = ["照顾优先，倾向先把人安顿好再谈收益"]
    elif main == "后勤规划型":
        lines = ["后勤意识强，喜欢先把食材、柴火和升级铺稳"]
    elif main == "记忆采集型":
        lines = ["很在意故事回声，会为了图鉴和记忆调整经营"]
    else:
        lines = ["对季节和庭院敏感，把旅馆看成会生长的地方"]
    if actions["complaints"] + actions["greet"] >= max(2, guests // 3):
        lines.append("愿意花时间听人说话，适合经营有温度的小店")
    if actions["meals"] + actions["baths"] >= actions["rooms"] + max(1, guests // 4):
        lines.append("偏爱用餐食和温泉解决问题，风格柔软")
    if actions["buys"] + actions["upgrades"] >= actions["prep"] + actions["wood"] + 2:
        lines.append("相信投入会换来未来，带一点长期主义")
    if risk == 0 and guests > 0:
        lines.append("秩序感很强，几乎不让待办过夜")
    if actions["garden_visits"] + actions["wood"] >= max(2, int(stats["days"]) // 3):
        lines.append("经常回到庭院，像是在用季节校准决策")
    return lines[:4]


def _annual_garden_note(stats: dict[str, Any]) -> str:
    season_days = stats["season_days"]
    richest = sorted(season_days.items(), key=lambda item: (-item[1], item[0]))[0]
    season_name = next(season["name"] for season in _SEASONS if season["id"] == richest[0])
    visits = stats["actions"]["garden_visits"]
    if visits:
        return "庭院记录：这一年你主动走进庭院{}次，{}留下的痕迹最厚。".format(visits, season_name)
    return "庭院记录：这一年庭院自己换过四季，但你很少专门停下来听它。"


def _end_day(game: dict[str, Any]) -> str:
    if not game["guests"]:
        return _start_day(game)
    lines = ["夜里，你把柜台灯调暗，开始结今天的账。"]
    income = 0
    memory_gain = 0
    unresolved = 0
    served_today = 0
    missed_rooms = 0
    missed_meals = 0
    missed_baths = 0
    for guest in game["guests"]:
        trait = _trait(guest)
        if not guest["room"]:
            guest["mood"] -= 3
            missed_rooms += 1
            lines.append("{}没有住下，只在门口点了点头。".format(guest["name"]))
            continue
        served_today += 1
        guest_income = int(guest["pay"])
        if guest["meal"]:
            guest_income += 4 + int(game["upgrades"]["kitchen"])
        else:
            guest["mood"] -= 1
            missed_meals += 1
        if guest["wants_bath"]:
            if guest["bath"]:
                guest_income += 4 + int(game["upgrades"]["onsen"])
            else:
                guest["mood"] -= 1
                missed_baths += 1
        if guest["complaint"]:
            guest["mood"] -= 2
            unresolved += 1
        if guest["mood"] >= 3:
            tip = max(0, min(8, 1 + guest["mood"] + int(trait.get("tip", 0))))
            guest_income += tip
            personal_memory = int(trait.get("memory", 0))
            if trait["id"] == "nostalgic":
                personal_memory += int(_event_value(game, "memory_bonus", 0))
            memory_gain += 1 + personal_memory
            unlocked = _unlock(game, guest["codex"])
            if personal_memory:
                lines.append("{}离店前留下{}钱小费，还讲了一段旧事。{}".format(guest["name"], tip, unlocked))
            else:
                lines.append("{}离店前留下{}钱小费。{}".format(guest["name"], tip, unlocked))
        elif guest["mood"] <= -3:
            refund = min(6, max(2, -guest["mood"]))
            guest_income -= refund
            lines.append("{}走得很轻，你退了{}钱。".format(guest["name"], refund))
        income += max(0, guest_income)
        game["served"] += 1
    game["money"] += income
    game["memory"] += memory_gain
    stats = _annual(game)
    stats["served"] += served_today
    stats["income"] += income
    stats["memory"] += memory_gain
    stats["missed_rooms"] += missed_rooms
    stats["missed_meals"] += missed_meals
    stats["missed_baths"] += missed_baths
    stats["unresolved_complaints"] += unresolved
    if unresolved:
        lines.append("还有{}件客诉没完全消化，夜里账本变重了一点。".format(unresolved))
    lines.append("今日收入{}钱，旅馆记忆+{}。".format(income, memory_gain))
    weather_line = _night_weather(game)
    if weather_line:
        lines.append(weather_line)
    rare = _maybe_rare(game, "night")
    if rare:
        lines.append(rare)
    ending = _maybe_ending(game)
    if ending:
        lines.append(ending)
    year_summary = _maybe_year_summary(game)
    if year_summary:
        lines.append(year_summary)
    lines.append(_start_day(game))
    return "\n".join(lines)


def _night_weather(game: dict[str, Any]) -> str:
    weather_id = game["weather"]
    if weather_id == "rain" and _chance(game, 35):
        if game["wood"] > 0:
            game["wood"] -= 1
            game["memory"] += 1
            _annual(game)["memory"] += 1
            return "夜雨压低屋檐，你添了一捆柴，前厅反而更安静。记忆+1。"
        return "夜雨压低屋檐，可柴棚空着，明天最好早些拾柴。"
    if weather_id == "wind" and _chance(game, 30):
        for guest in game["guests"]:
            if guest["room"] and _chance(game, 35):
                guest["complaint"] = True
        return "风把几扇窗吹得发响，你在账本旁记下：明天先查窗扣。"
    if weather_id == "fog" and _chance(game, 25):
        game["memory"] += 1
        _annual(game)["memory"] += 1
        return "雾夜没有客人再说话，但门廊灯亮到很晚。记忆+1。"
    if weather_id == "snow" and _chance(game, 35):
        game["wood"] = max(0, game["wood"] - 1)
        game["money"] += 2
        return "雪夜多耗了一点柴，清晨门口却多出两枚硬币。"
    return ""


def _maybe_rare(game: dict[str, Any], trigger: str) -> str:
    base = 4
    if trigger == "garden":
        base += 6 + int(game["upgrades"]["garden"]) * 3
    if trigger == "front":
        base += 3 + int(game["upgrades"]["sign"]) * 2
    if trigger == "kitchen":
        base += 4 + int(game["upgrades"]["kitchen"]) * 2
    if trigger == "onsen":
        base += 4 + int(game["upgrades"]["onsen"]) * 2
    if trigger == "rooms":
        base += 4 + int(game["upgrades"]["rooms"]) * 2
    if trigger == "night":
        base += min(8, len(game["codex"]))
    if game["weather"] == "fog":
        base += 4
    if not _chance(game, base):
        return ""
    possible = []
    for event in _RARE_EVENTS:
        if event["id"] in game["codex"]:
            continue
        if trigger not in event.get("triggers", []):
            continue
        if event["weather"] is None or event["weather"] == game["weather"]:
            possible.append(event)
    if not possible:
        return ""
    event = possible[_randrange(game, len(possible))]
    bonus = event["bonus"]
    for key, value in bonus.items():
        game[key] = game.get(key, 0) + value
        if key == "memory":
            _annual(game)["memory"] += value
    _annual(game)["rare_events"] += 1
    unlocked = _unlock(game, event["id"])
    return "稀有事件：{}。{}\n{}".format(event["title"], event["line"], unlocked)


def _maybe_ending(game: dict[str, Any]) -> str:
    if game["flags"].get("ending_seen"):
        return ""
    if game["day"] < 14:
        return ""
    game["flags"]["ending_seen"] = True
    codex_count = len(game["codex"])
    if codex_count >= 10 or game["memory"] >= 22:
        return (
            "第十四夜过后，账本合上又自己翻开：这不是最赚钱的旅馆，"
            + "但很多人能准确说出这里的一盏灯、一碗汤和一句被听完的话。"
            + "你可以继续经营。"
        )
    return (
        "第十四夜过后，账本提醒你：钱够让旅馆开门，记忆才会让人回来。"
        + "你可以继续经营，把空白慢慢补上。"
    )


def _unlock(game: dict[str, Any], key: str) -> str:
    if key not in _CODEX or key in game["codex"]:
        return ""
    game["codex"].append(key)
    _annual(game)["codex"] += 1
    entry = _CODEX[key]
    return "图鉴新增《{}》。".format(entry["title"])
