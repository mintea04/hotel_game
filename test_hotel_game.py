import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

import hotel_game


ROOT = os.path.dirname(os.path.abspath(__file__))


def status_from(text):
    return json.loads(text.strip().splitlines()[-1])


class HotelGameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["HOTEL_GAME_SAVE"] = os.path.join(self.tmp.name, "save.json")
        hotel_game.new_game("test-seed")

    def test_public_api_and_save(self):
        self.assertEqual(hotel_game.__all__, ["new_game", "cmd"])
        out = hotel_game.cmd("状态")
        status = status_from(out)
        self.assertEqual(status["day"], 1)
        self.assertTrue(status["saved"])
        self.assertTrue(os.path.exists(os.environ["HOTEL_GAME_SAVE"]))

    def test_deterministic_from_seed_and_commands(self):
        commands = [
            "客人",
            "去 客房; 安排 全部",
            "去 厨房; 做饭 全部",
            "去 前厅; 客诉 全部",
            "结束一天",
        ]
        first = [hotel_game.new_game("same")]
        first.extend(hotel_game.cmd(command) for command in commands)
        second = [hotel_game.new_game("same")]
        second.extend(hotel_game.cmd(command) for command in commands)
        self.assertEqual(first, second)

    def test_batch_commands_have_one_status_line(self):
        out = hotel_game.cmd("去 客房; 安排 全部; 去 厨房; 做饭 全部")
        status = status_from(out)
        self.assertIn("[1]", out)
        self.assertEqual(status["loc"], "厨房")
        self.assertLessEqual(status["todo"]["room"], status["guests"])

    def test_batch_rethen_does_not_create_extra_command(self):
        out = hotel_game.cmd("状态 再然后 状态")
        self.assertIn("[1]", out)
        self.assertIn("[2]", out)
        self.assertNotIn("[3]", out)
        self.assertNotIn("它还不是旅馆听得懂的指令", out)

    def test_guest_traits_and_public_day_event_status(self):
        out = hotel_game.cmd("客人")
        status = status_from(out)
        self.assertIn("event", status)
        self.assertIn("inspiration", status)
        self.assertIn("rate", status)
        self.assertIn("promise", status)
        self.assertIn("rooms", status)
        self.assertIn("性格：", out)
        self.assertIn("愿望：", out)

    def test_standard_care_and_unassigned_room_warning(self):
        out = hotel_game.cmd("照顾 全部")
        status = status_from(out)
        self.assertIn("标准接待开始", out)
        self.assertEqual(status["todo"]["room"], 0)
        hotel_game.new_game("warning-seed")
        out = hotel_game.cmd("去 厨房; 做饭 全部; 结束一天")
        self.assertIn("风险提醒", out)
        self.assertIn("未安排房间的客人不会入住", out)

    def test_end_day_requires_confirmation_when_risky(self):
        hotel_game.new_game("warning-seed")
        warned = hotel_game.cmd("结束一天")
        self.assertIn("确认结束", warned)
        self.assertEqual(status_from(warned)["day"], 1)
        ended = hotel_game.cmd("确认结束")
        self.assertIn("今日收入", ended)
        self.assertEqual(status_from(ended)["day"], 2)

    def test_capacity_warning_and_services_require_room(self):
        hotel_game.new_game("staff-seed")
        advice = hotel_game.cmd("建议")
        self.assertIn("今天房间不够", advice)
        kitchen = hotel_game.cmd("去 厨房; 做饭 全部")
        self.assertIn("只给已安排房间的住客上餐", kitchen)
        onsen = hotel_game.cmd("去 温泉; 温泉 全部")
        self.assertIn("已安排房间的住客", onsen)
        out = hotel_game.cmd("照顾 全部")
        status = status_from(out)
        self.assertEqual(status["rooms"], {"cap": 2, "used": 2})
        self.assertEqual(status["todo"]["room"], 1)
        self.assertEqual(status["todo"]["meal"], 0)
        self.assertLessEqual(out.count("端上餐食"), status["rooms"]["cap"])

    def test_advice_respects_energy_and_standard_care_prioritizes_complaints(self):
        hotel_game.new_game("energy-seed")
        hotel_game._GAME["energy"] = 3
        for guest in hotel_game._GAME["guests"]:
            guest["complaint"] = True
            guest["wants_bath"] = True
        advice = hotel_game.cmd("建议")
        self.assertIn("体力不够照顾全部", advice)
        self.assertNotIn("可以直接说：照顾 全部", advice)
        out = hotel_game.cmd("照顾 全部")
        self.assertLess(out.find("【客诉】"), out.find("【餐食】"))

    def test_advice_recommends_rate_and_promise_from_public_state(self):
        hotel_game.new_game("regular-seed")
        bath_day = hotel_game.cmd("建议")
        self.assertIn("建议策略：可说“定价 溢价；承诺 温泉”", bath_day)
        hotel_game.new_game("staff-seed")
        tight_day = hotel_game.cmd("建议")
        self.assertIn("建议策略：可说“定价 亲民；承诺 礼宾”", tight_day)
        self.assertIn("固定维护", tight_day)

    def test_revenue_strategy_commands_and_promise_settlement(self):
        hotel_game.new_game("regular-seed")
        set_plan = hotel_game.cmd("定价 溢价; 承诺 温泉")
        status = status_from(set_plan)
        self.assertEqual(status["rate"], "溢价")
        self.assertEqual(status["promise"], "温泉")
        revenue = hotel_game.cmd("收益")
        self.assertIn("今日收益策略：定价《溢价》，承诺《温泉》", revenue)
        out = hotel_game.cmd("照顾 全部; 结束一天")
        self.assertIn("承诺《温泉》兑现", out)
        self.assertIn("其中房费", out)

    def test_rate_carries_into_next_day_arrivals(self):
        hotel_game.new_game("rate-seed")
        out = hotel_game.cmd("定价 溢价; 确认结束")
        self.assertIn("挂牌价是《溢价》", out)
        self.assertEqual(status_from(out)["rate"], "溢价")

    def test_fixed_costs_include_weekly_linen(self):
        hotel_game.new_game("linen-seed")
        hotel_game._GAME["day"] = 7
        out = hotel_game.cmd("确认结束")
        self.assertIn("灯油与洗涤", out)
        self.assertIn("布草维护", out)

    def test_shop_daily_limit_and_escalating_price(self):
        hotel_game.new_game("shop-seed")
        bought = hotel_game.cmd("买 食材 4")
        status = status_from(bought)
        self.assertIn("买入4份食材，花18钱", bought)
        self.assertEqual(status["shop"]["food_left"], 0)
        blocked = hotel_game.cmd("买 食材 1")
        self.assertIn("食材已经买完", blocked)
        hotel_game.cmd("确认结束")
        next_day = status_from(hotel_game.cmd("状态"))
        self.assertEqual(next_day["shop"]["food_left"], 4)
        hotel_game._GAME["today_event"] = ""
        fresh_price = hotel_game.cmd("买 食材 1")
        self.assertIn("买入1份食材，花4钱", fresh_price)

    def test_manual_prep_and_wood_add_quality_bonus(self):
        hotel_game.new_game("quality-seed")
        meal = hotel_game.cmd("备料; 安排 全部; 做饭 1")
        self.assertIn("下一次餐食心情+1", meal)
        self.assertIn("亲手备料的季节味道被尝出来了", meal)
        hotel_game.new_game("quality-seed")
        bath = hotel_game.cmd("拾柴; 安排 全部; 温泉 全部")
        self.assertIn("下一次温泉心情+1", bath)
        self.assertIn("亲手挑回的柴让水汽更稳", bath)

    def test_advice_understands_shop_limits_and_wind_wood(self):
        hotel_game.new_game("limit-advice")
        game = hotel_game._GAME
        game["food"] = 0
        game["wood"] = 0
        game["shop_bought"] = {"food": 4, "wood": 3}
        game["weather"] = "wind"
        for guest in game["guests"]:
            guest["wants_bath"] = True
        advice = hotel_game.cmd("建议")
        self.assertIn("商店食材限购已接近上限", advice)
        self.assertIn("商店柴火限购已接近上限", advice)
        self.assertIn("风天拾柴额外顺手", advice)

    def test_personality_distinguishes_purchase_and_manual_logistics(self):
        stats = hotel_game._new_annual_stats()
        stats["guests"] = 8
        stats["actions"]["buys"] = 8
        purchase_lines = hotel_game._personality_lines(stats)
        self.assertIn("采购型明显", "；".join(purchase_lines))
        stats = hotel_game._new_annual_stats()
        stats["guests"] = 8
        stats["actions"]["prep"] = 4
        stats["actions"]["wood"] = 4
        manual_lines = hotel_game._personality_lines(stats)
        self.assertIn("勤恳后勤型明显", "；".join(manual_lines))

    def test_clear_actions_auto_move_and_meals_have_seasonal_menu(self):
        hotel_game.new_game("test-seed")
        out = hotel_game.cmd("安排 全部; 做饭 全部")
        status = status_from(out)
        self.assertEqual(status["loc"], "厨房")
        self.assertIn("你先绕到客房走廊", out)
        self.assertIn("你先绕到厨房，系上围裙", out)
        self.assertIn("端上餐食《", out)
        bought = hotel_game.cmd("买 食材 1")
        self.assertIn("你先绕到街角商店", bought)

    def test_garden_moment_explains_inspiration_effect(self):
        hotel_game.new_game("garden-0")
        out = hotel_game.cmd("去 庭院")
        self.assertIn("庭院小记", out)
        self.assertIn("效果很明确", out)
        self.assertIn("可说：做饭 全部", out)

    def test_ledger_reminder_reaches_advice(self):
        out = hotel_game.cmd("账本提醒")
        self.assertIn("今日计划", out)

    def test_advice_named_save_and_backup(self):
        advice = hotel_game.cmd("建议")
        self.assertIn("今日计划", advice)
        saved = hotel_game.cmd("保存为 一周目")
        self.assertIn("已保存命名存档《一周目》", saved)
        hotel_game.cmd("结束一天")
        loaded = hotel_game.cmd("读档 一周目")
        self.assertIn("已先备份当前进度", loaded)
        self.assertEqual(status_from(loaded)["day"], 1)
        listing = hotel_game.cmd("存档列表")
        self.assertIn("一周目", listing)
        backup = hotel_game.cmd("备份存档")
        self.assertIn("已备份当前进度", backup)

    def test_staff_and_regular_memory_lines(self):
        hotel_game.new_game("staff-seed")
        empty = hotel_game.cmd("帮手")
        self.assertIn("还没有固定帮手", empty)
        staff = hotel_game.cmd("去 厨房; 备料; 备料; 备料")
        self.assertIn("帮手传闻", staff)
        self.assertIn("结识帮手", staff)
        self.assertEqual(status_from(staff)["staff"], 1)
        roster = hotel_game.cmd("帮手")
        self.assertIn("厨房阿姨", roster)
        hotel_game.new_game("regular-seed")
        regular = hotel_game.cmd("照顾 全部; 结束一天")
        self.assertIn("下次还想住同一间", regular)

    def test_returning_guest_updates_last_seen_even_when_unhappy(self):
        hotel_game.new_game("regular-last-seen")
        game = hotel_game._GAME
        game["regulars"] = [
            {
                "key": "r1",
                "name": "白灯",
                "type": "bookkeeper",
                "trait": "quiet",
                "visits": 1,
                "affinity": 5,
                "last_seen": 0,
            }
        ]
        guest = {
            "name": "白灯",
            "type": "bookkeeper",
            "trait": "quiet",
            "regular_key": "r1",
            "mood": 0,
        }
        line = hotel_game._remember_regular(game, guest)
        self.assertIn("没有多说", line)
        self.assertEqual(game["regulars"][0]["last_seen"], game["day"])
        self.assertEqual(game["regulars"][0]["visits"], 2)

    def test_returning_guest_arrival_echo_uses_last_stay(self):
        hotel_game.new_game("regular-echo")
        game = hotel_game._GAME
        guest = {
            "name": "白灯",
            "returning": True,
            "returning_visit_no": 2,
            "regular_last_stay": {
                "weather": "雨",
                "menu": "薄荷冷汤",
                "promise": "餐食",
            },
        }
        line = hotel_game._returning_arrival_line(game, guest)
        self.assertIn("旧钥匙钩", line)
        self.assertIn("《薄荷冷汤》", line)
        self.assertIn("承诺《餐食》", line)
        self.assertEqual(guest["note"], line)

    def test_returning_guest_third_sleep_and_fourth_gift(self):
        hotel_game.new_game("regular-scenes")
        game = hotel_game._GAME
        game["regulars"] = [
            {
                "key": "r1",
                "name": "陆眠",
                "type": "sleepless_poet",
                "trait": "light_sleeper",
                "visits": 2,
                "affinity": 9,
                "last_seen": 0,
            },
            {
                "key": "r2",
                "name": "林青",
                "type": "botanist",
                "trait": "nostalgic",
                "visits": 3,
                "affinity": 12,
                "last_seen": 0,
            },
        ]
        sleeper = {
            "name": "陆眠",
            "type": "sleepless_poet",
            "trait": "light_sleeper",
            "regular_key": "r1",
            "mood": 5,
            "meal": True,
            "bath": True,
            "complaint": False,
        }
        line = hotel_game._remember_regular(game, sleeper)
        self.assertIn("终于睡到天亮", line)
        self.assertEqual(game["regulars"][0]["visits"], 3)
        botanist = {
            "name": "林青",
            "type": "botanist",
            "trait": "nostalgic",
            "regular_key": "r2",
            "mood": 5,
            "meal": True,
            "bath": False,
            "complaint": False,
        }
        before_memory = game["memory"]
        gift = hotel_game._remember_regular(game, botanist)
        self.assertIn("绣球干花", gift)
        self.assertIn("记忆+2", gift)
        self.assertEqual(game["memory"], before_memory + 2)
        self.assertTrue(game["regulars"][1]["gifted"])

    def test_window_check_flag_is_actionable(self):
        hotel_game.new_game("window-seed")
        game = hotel_game._GAME
        game["flags"]["check_windows"] = True
        advice = hotel_game.cmd("建议")
        self.assertIn("检查窗扣", advice)
        out = hotel_game.cmd("去 客房; 打扫")
        self.assertIn("窗扣", out)
        self.assertFalse(game["flags"]["check_windows"])

    def test_time_seasons_garden_and_year_summary(self):
        start = status_from(hotel_game.cmd("状态"))
        self.assertEqual(start["season"], "春")
        self.assertEqual(start["time"], "清晨")
        after_action = status_from(hotel_game.cmd("去 客房; 安排 1"))
        self.assertEqual(after_action["time"], "上午")
        garden = hotel_game.cmd("去 庭院")
        self.assertIn("庭院小记", garden)
        for _ in range(27):
            hotel_game.cmd("确认结束")
        out = hotel_game.cmd("确认结束")
        self.assertIn("年度总结：第1年结束", out)
        self.assertIn("OCC", out)
        self.assertIn("ADR", out)
        self.assertIn("RevPAR", out)
        status = status_from(out)
        self.assertEqual(status["year"], 2)
        self.assertEqual(status["season"], "春")

    def test_owner_participation_reservation_note_and_memory_seed(self):
        hotel_game.new_game("owner-seed")
        reserved = hotel_game.cmd("预约客人 柳川 喜欢热茶和晚饭，想在前厅聊一会儿")
        self.assertIn("前厅收到一张预约卡：柳川", reserved)
        self.assertEqual(status_from(reserved)["reservations"], 1)
        note = hotel_game.cmd("主人留言 今天请先照顾赶路很累的人")
        self.assertIn("馆主留言夹进手账", note)
        advice = hotel_game.cmd("建议")
        self.assertIn("馆主留言", advice)
        seed = hotel_game.cmd("种下记忆 庭院石灯旁放着一枚旧铜铃")
        self.assertIn("一粒记忆", seed)
        garden = hotel_game.cmd("去 庭院")
        self.assertIn("馆主种下的记忆发芽", garden)
        self.assertEqual(status_from(garden)["memory_seeds"], 0)
        book = hotel_game.cmd("查看预约")
        self.assertIn("等待抵达的预约", book)
        arrival_day = hotel_game._GAME["reservations"][0]["arrival_day"]
        out = ""
        while hotel_game._GAME["day"] < arrival_day:
            out = hotel_game.cmd("确认结束")
        self.assertIn("预约客人：柳川", out)
        guests = hotel_game.cmd("客人")
        self.assertIn("预约客", guests)
        self.assertIn("柳川", guests)
        checkout = hotel_game.cmd("安排 柳川; 客诉 柳川; 做饭 柳川; 招呼; 确认结束")
        self.assertIn("预约卡折回去", checkout)
        self.assertIn("旅馆记忆+1", checkout)
        preview = hotel_game.cmd("年度总结")
        self.assertIn("馆主参与", preview)
        self.assertIn("预约照顾", preview)

    def test_blind_generator_output_runs(self):
        target = os.path.join(self.tmp.name, "hotel_game_blind.py")
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "make_blind.py"), os.path.join(ROOT, "hotel_game.py"), target],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertTrue(os.path.exists(target))
        spec = importlib.util.spec_from_file_location("hotel_game_blind_test", target)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        os.environ["HOTEL_GAME_SAVE"] = os.path.join(self.tmp.name, "blind-save.json")
        out = module.new_game("blind-seed")
        self.assertIn("cmd", module.__all__)
        self.assertEqual(status_from(out)["day"], 1)
        self.assertEqual(status_from(module.cmd("状态"))["day"], 1)


if __name__ == "__main__":
    unittest.main()
