"""
test_suite.py
===============
مجموعة اختبارات تتحقق من صحة كل المنطق البرمجي (بدون أي اتصال شبكي) —
شغّلها بعد أي تعديل في الكود للتأكد أنك لم تكسر شيئًا.

التشغيل:
    python3 -m unittest test_suite.py -v
"""

import json
import os
import tempfile
import unittest

from market_scanner import MarketScanner, ScannerConfig, SignalType
from risk_manager import OpenPositionInfo, RiskManager, RiskConfig
from startup_reconciliation import StartupReconciler
from telegram_notifier import MonthlyProfitCounter


class TestMarketScanner(unittest.TestCase):
    def setUp(self):
        self.cfg = ScannerConfig(std_period=20, entry_std_multiplier=2.0, max_allowed_spread_pips=1.0)
        self.scanner = MarketScanner(self.cfg, symbols=["EURUSD"])

    def test_no_signal_before_window_full(self):
        """لا إشارة قبل امتلاء نافذة الحساب"""
        sig = self.scanner.on_price("EURUSD", 1.0850, 1.0851)
        self.assertEqual(sig, SignalType.NONE)

    def test_no_signal_on_flat_prices(self):
        """لا إشارة عند أسعار مستقرة تمامًا (انحراف معياري = صفر)"""
        for _ in range(25):
            sig = self.scanner.on_price("EURUSD", 1.0850, 1.0851)
        self.assertEqual(sig, SignalType.NONE)

    def test_buy_signal_on_extreme_drop(self):
        """
        إشارة شراء عند انحراف سفلي متطرف — نافذة كبيرة (20) حتى لا تُهيمن
        القيمة المتطرفة الأخيرة على حساب متوسطها/انحرافها الخاص (وهذا نفس
        سلوك النافذة المتحركة الحقيقي في market_scanner.py: كل سعر جديد
        يُضاف للنافذة قبل حساب الإشارة عليه).
        """
        for _ in range(19):
            self.scanner.on_price("EURUSD", 1.0850, 1.0851)
        sig = self.scanner.on_price("EURUSD", 1.0700, 1.0701)  # هبوط حاد نسبةً لـ19 سعرًا مستقرًا
        self.assertEqual(sig, SignalType.BUY_REVERSION)

    def test_no_signal_on_wide_spread(self):
        """لا إشارة إذا كان السبريد أعلى من الحد المسموح، حتى لو الانحراف كبير"""
        for _ in range(19):
            self.scanner.on_price("EURUSD", 1.0850, 1.0851)
        sig = self.scanner.on_price("EURUSD", 1.0700, 1.0750)  # سبريد ضخم 50 نقطة
        self.assertEqual(sig, SignalType.NONE)

    def test_unknown_symbol_ignored(self):
        """رمز غير مُهيَّأ في القائمة يُتجاهل بأمان بدل رمي خطأ"""
        sig = self.scanner.on_price("USDJPY", 150.0, 150.01)
        self.assertEqual(sig, SignalType.NONE)


class TestRiskManager(unittest.TestCase):
    def _make_cfg(self, **overrides):
        defaults = dict(
            max_daily_drawdown_pct=4.0, max_concurrent_positions=2,
            risk_per_trade_pct=1.0, target_symbols=["EURUSD", "GBPUSD"],
            use_fixed_volume=True, trade_volume_units=1000,
        )
        defaults.update(overrides)
        return RiskConfig(**defaults)

    def test_fixed_volume_mode_ignores_equity(self):
        """في وضع الحجم الثابت، الحجم لا يتغير مهما كان الرصيد"""
        rm = RiskManager(self._make_cfg(use_fixed_volume=True, trade_volume_units=1000),
                          on_emergency_close_all=lambda r: None)
        self.assertEqual(rm.calculate_position_size_lots(4.0), 0.01)
        rm.update_account_info(balance=50.0, equity=50.0)
        self.assertEqual(rm.calculate_position_size_lots(4.0), 0.01)

    def test_dynamic_volume_scales_with_equity(self):
        """في الوضع الديناميكي، الحجم يتغيّر مع الرصيد"""
        rm = RiskManager(self._make_cfg(use_fixed_volume=False, risk_per_trade_pct=1.0),
                          on_emergency_close_all=lambda r: None)
        rm.update_account_info(balance=1000.0, equity=1000.0)
        lot_1000 = rm.calculate_position_size_lots(stop_loss_pips=4.0)
        rm.update_account_info(balance=2000.0, equity=2000.0)
        lot_2000 = rm.calculate_position_size_lots(stop_loss_pips=4.0)
        self.assertGreater(lot_2000, lot_1000)

    def test_daily_drawdown_triggers_emergency_close(self):
        """تجاوز حد التراجع اليومي يُفعّل الإغلاق الطارئ مرة واحدة فقط"""
        triggered = []
        rm = RiskManager(self._make_cfg(max_daily_drawdown_pct=4.0),
                          on_emergency_close_all=lambda r: triggered.append(r))
        rm.update_account_info(balance=1000.0, equity=1000.0)  # بداية اليوم
        rm.update_account_info(balance=960.0, equity=960.0)    # خسارة 4% بالضبط
        self.assertEqual(len(triggered), 1)
        self.assertTrue(rm.trading_halted)

        # لا يتكرر التنبيه لنفس اليوم حتى لو استمرت الخسارة
        rm.update_account_info(balance=950.0, equity=950.0)
        self.assertEqual(len(triggered), 1)

    def test_max_concurrent_positions_blocks_new_trade(self):
        """لا صفقات جديدة بعد الوصول للحد الأقصى للصفقات المتزامنة"""
        rm = RiskManager(self._make_cfg(max_concurrent_positions=1),
                          on_emergency_close_all=lambda r: None)
        self.assertTrue(rm.can_open_new_position())
        rm.register_open_position(OpenPositionInfo(
            position_id=1, symbol_name="EURUSD", symbol_id=1, is_buy=True, volume_lots=0.01
        ))
        self.assertFalse(rm.can_open_new_position())
        rm.unregister_position(1)
        self.assertTrue(rm.can_open_new_position())


class TestStartupReconciler(unittest.TestCase):
    def setUp(self):
        self.corrections = []
        self.reconciler = StartupReconciler(
            sl_pips=4.0, tp_pips=6.0, pip_size=0.0001,
            amend_sl_tp_fn=lambda pid, sl, tp: self.corrections.append((pid, sl, tp)),
        )

    def test_healthy_position_not_touched(self):
        pos = {"position_id": 1, "symbol_name": "EURUSD", "is_buy": True,
               "entry_price": 1.0850, "stop_loss": 1.0846, "take_profit": 1.0856}
        finding = self.reconciler.check_position(pos)
        self.assertFalse(finding.was_corrected)
        self.assertEqual(len(finding.issues), 0)

    def test_missing_sl_gets_corrected(self):
        pos = {"position_id": 2, "symbol_name": "EURUSD", "is_buy": True,
               "entry_price": 1.0850, "stop_loss": None, "take_profit": 1.0856}
        finding = self.reconciler.check_position(pos)
        self.assertTrue(finding.was_corrected)
        self.assertIsNotNone(finding.corrected_sl)
        self.assertLess(finding.corrected_sl, pos["entry_price"])  # SL شراء يجب أن يكون تحت الدخول

    def test_inverted_sl_on_sell_position_corrected(self):
        """أخطر سيناريو: وقف خسارة في الجهة الخاطئة على صفقة بيع"""
        pos = {"position_id": 3, "symbol_name": "EURUSD", "is_buy": False,
               "entry_price": 1.0850, "stop_loss": 1.0800, "take_profit": 1.0800}
        finding = self.reconciler.check_position(pos)
        self.assertTrue(finding.was_corrected)
        self.assertGreater(finding.corrected_sl, pos["entry_price"])  # SL بيع يجب أن يكون فوق الدخول

    def test_run_applies_corrections_via_callback(self):
        positions = [
            {"position_id": 5, "symbol_name": "GBPUSD", "is_buy": True,
             "entry_price": 1.2700, "stop_loss": None, "take_profit": None},
        ]
        self.reconciler.run(positions)
        self.assertEqual(len(self.corrections), 1)
        self.assertEqual(self.corrections[0][0], 5)


class TestMonthlyProfitCounter(unittest.TestCase):
    def setUp(self):
        self.tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp_file.close()

    def tearDown(self):
        if os.path.exists(self.tmp_file.name):
            os.remove(self.tmp_file.name)

    def test_accumulates_profit_across_trades(self):
        counter = MonthlyProfitCounter(self.tmp_file.name)
        counter.add_trade_result(10.5)
        counter.add_trade_result(-3.2)
        result = counter.add_trade_result(7.0)
        self.assertAlmostEqual(result["total_profit"], 14.3, places=2)
        self.assertEqual(result["trade_count"], 3)

    def test_persists_across_new_instances(self):
        """التأكد أن العداد يُقرأ من الملف بعد إعادة إنشاء الكائن (محاكاة إعادة تشغيل)"""
        counter1 = MonthlyProfitCounter(self.tmp_file.name)
        counter1.add_trade_result(20.0)

        counter2 = MonthlyProfitCounter(self.tmp_file.name)  # كائن جديد، نفس الملف
        self.assertAlmostEqual(counter2.total_profit, 20.0, places=2)

    def test_resets_on_new_month(self):
        """محاكاة تغيّر الشهر يدويًا للتأكد من التصفير التلقائي"""
        counter = MonthlyProfitCounter(self.tmp_file.name)
        counter.add_trade_result(50.0)

        # نحاكي شهرًا قديمًا يدويًا في الملف
        with open(self.tmp_file.name, "w") as f:
            json.dump({"month_key": "2000-01", "total_profit": 999.0, "trade_count": 5}, f)

        counter2 = MonthlyProfitCounter(self.tmp_file.name)
        self.assertEqual(counter2.total_profit, 0.0)  # صُفِّر تلقائيًا لأن الشهر تغيّر
        self.assertEqual(counter2.trade_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
