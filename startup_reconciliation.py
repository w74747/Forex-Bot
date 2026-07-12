"""
startup_reconciliation.py
===========================
Post-Restore Health Check — يعمل مرة واحدة فقط بعد كل إقلاع للبوت
(سواء بسبب تحديث كود، انقطاع، أو أي إعادة تشغيل من Railway).

الفكرة: بدل الاعتماد على أي حالة محلية قد تكون فُقدت، نسأل الخادم
مباشرة "ما هي صفقاتي المفتوحة فعليًا؟" عبر ProtoOAReconcileReq
(الخادم = مصدر الحقيقة الوحيد الموثوق).

لكل صفقة مُستردة، نتحقق من:
  1. هل يوجد وقف خسارة (SL) أصلاً؟ → إن غاب، نُعيّنه فورًا
  2. هل يوجد جني ربح (TP) أصلاً؟ → إن غاب، نُعيّنه فورًا
  3. هل SL في الجهة الصحيحة من سعر الدخول؟ (أسفل للشراء، أعلى للبيع)
     → إن كان معكوسًا (خطأ فادح يعرّض الحساب لخسارة غير محدودة)، نُصححه فورًا
  4. هل SL/TP ضمن نطاق معقول (ليس بعيدًا/قريبًا بشكل غير منطقي)؟
     → نُبلّغ فقط دون تصحيح تلقائي (قد يكون تعديلاً يدويًا مقصودًا)

يُنتج تقريرًا نصيًا واحدًا يُرسَل لتيليجرام يلخّص كل ما وُجد وما تم تصحيحه.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger("forex_bot.startup_reconciliation")


@dataclass
class ReconciliationFinding:
    position_id: int
    symbol_name: str
    is_buy: bool
    entry_price: float
    original_sl: Optional[float]
    original_tp: Optional[float]
    issues: List[str] = field(default_factory=list)
    corrected_sl: Optional[float] = None
    corrected_tp: Optional[float] = None
    was_corrected: bool = False


class StartupReconciler:
    def __init__(self, sl_pips: float, tp_pips: float, pip_size: float,
                 amend_sl_tp_fn: Callable[[int, Optional[float], Optional[float]], None],
                 reasonable_distance_multiplier: float = 3.0):
        """
        sl_pips / tp_pips: القيم المعيارية المتوقعة من استراتيجيتنا (نفس قيم main.py)
        amend_sl_tp_fn: الدالة الفعلية لإرسال التصحيح (openapi.amend_position_sl_tp)
        reasonable_distance_multiplier: أي SL/TP أبعد من هذا الضعف عن القيمة
            المعيارية يُعتبر "غير معتاد" ويُذكر في التقرير فقط دون تصحيح تلقائي
        """
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.pip_size = pip_size
        self.amend_sl_tp_fn = amend_sl_tp_fn
        self.reasonable_distance_multiplier = reasonable_distance_multiplier

    def expected_sl_tp(self, is_buy: bool, entry_price: float) -> tuple[float, float]:
        if is_buy:
            return (entry_price - self.sl_pips * self.pip_size,
                    entry_price + self.tp_pips * self.pip_size)
        return (entry_price + self.sl_pips * self.pip_size,
                entry_price - self.tp_pips * self.pip_size)

    def check_position(self, pos: dict) -> ReconciliationFinding:
        is_buy = pos["is_buy"]
        entry_price = pos["entry_price"]
        finding = ReconciliationFinding(
            position_id=pos["position_id"],
            symbol_name=pos["symbol_name"],
            is_buy=is_buy,
            entry_price=entry_price,
            original_sl=pos["stop_loss"],
            original_tp=pos["take_profit"],
        )

        expected_sl, expected_tp = self.expected_sl_tp(is_buy, entry_price)
        new_sl, new_tp = None, None

        # 1) فحص غياب SL
        if pos["stop_loss"] is None:
            finding.issues.append("لا يوجد وقف خسارة إطلاقًا — تعرّض غير محمي")
            new_sl = expected_sl
        else:
            # 2) فحص أن SL في الجهة الصحيحة
            sl_wrong_side = (is_buy and pos["stop_loss"] >= entry_price) or \
                             (not is_buy and pos["stop_loss"] <= entry_price)
            if sl_wrong_side:
                finding.issues.append(
                    f"⚠️ وقف الخسارة في الجهة الخاطئة! ({pos['stop_loss']:.5f}) — خطر جسيم"
                )
                new_sl = expected_sl
            else:
                # 3) فحص المسافة غير المعتادة (تبليغ فقط، بدون تصحيح تلقائي)
                actual_sl_pips = abs(entry_price - pos["stop_loss"]) / self.pip_size
                if actual_sl_pips > self.sl_pips * self.reasonable_distance_multiplier or \
                   actual_sl_pips < self.sl_pips / self.reasonable_distance_multiplier:
                    finding.issues.append(
                        f"وقف الخسارة بمسافة غير معتادة: {actual_sl_pips:.1f} نقطة "
                        f"(المتوقع ~{self.sl_pips}) — لم يُعدَّل تلقائيًا"
                    )

        # 4) فحص غياب TP (نفس المنطق)
        if pos["take_profit"] is None:
            finding.issues.append("لا يوجد جني ربح محدد")
            new_tp = expected_tp
        else:
            tp_wrong_side = (is_buy and pos["take_profit"] <= entry_price) or \
                             (not is_buy and pos["take_profit"] >= entry_price)
            if tp_wrong_side:
                finding.issues.append(
                    f"⚠️ جني الربح في الجهة الخاطئة! ({pos['take_profit']:.5f})"
                )
                new_tp = expected_tp

        if new_sl is not None or new_tp is not None:
            finding.corrected_sl = new_sl if new_sl is not None else pos["stop_loss"]
            finding.corrected_tp = new_tp if new_tp is not None else pos["take_profit"]
            finding.was_corrected = True

        return finding

    def run(self, positions: List[dict]) -> List[ReconciliationFinding]:
        logger.info("[Reconciliation] بدء فحص %d صفقة مُستردة من الخادم", len(positions))
        findings = []
        for pos in positions:
            finding = self.check_position(pos)
            findings.append(finding)
            if finding.was_corrected:
                logger.warning("[Reconciliation] تصحيح صفقة %s: SL=%s TP=%s",
                                finding.position_id, finding.corrected_sl, finding.corrected_tp)
                self.amend_sl_tp_fn(finding.position_id, finding.corrected_sl, finding.corrected_tp)
            elif finding.issues:
                logger.info("[Reconciliation] ملاحظات على صفقة %s (بدون تصحيح): %s",
                            finding.position_id, finding.issues)
            else:
                logger.info("[Reconciliation] صفقة %s سليمة تمامًا", finding.position_id)
        return findings

    @staticmethod
    def build_telegram_report(findings: List[ReconciliationFinding]) -> str:
        if not findings:
            return "✅ <b>فحص ما بعد الإقلاع</b>\nلا توجد أي صفقات مفتوحة حاليًا على الخادم."

        lines = [f"🔍 <b>فحص ما بعد الإقلاع</b> — {len(findings)} صفقة مُستردة\n"]
        corrected_count = sum(1 for f in findings if f.was_corrected)
        clean_count = sum(1 for f in findings if not f.issues)

        for f in findings:
            status = "✅ سليمة" if not f.issues else ("🛠️ تم التصحيح" if f.was_corrected else "ℹ️ ملاحظة")
            lines.append(f"— {f.symbol_name} #{f.position_id} ({'شراء' if f.is_buy else 'بيع'}): {status}")
            for issue in f.issues:
                lines.append(f"   • {issue}")

        lines.append(f"\nالخلاصة: {clean_count} سليمة، {corrected_count} صُحِّحت تلقائيًا، "
                     f"{len(findings) - clean_count - corrected_count} ملاحظات فقط.")
        return "\n".join(lines)
