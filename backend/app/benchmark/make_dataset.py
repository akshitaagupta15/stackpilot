"""Generates the synthetic invoice dataset deterministically (seed fixed).
Run:  python -m app.benchmark.make_dataset
Output: app/benchmark/data/invoices_v1.jsonl  (UTF-8, one JSON object per line)
NOTE: templated + synthetic. Add messier, real-looking examples before trusting results."""
import json
import random
from pathlib import Path

OUT = Path(__file__).parent / "data" / "invoices_v1.jsonl"
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
HI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
             "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
VENDORS_EN = ["Sharma Traders", "Bright Office Supplies", "Delta Logistics Pvt Ltd", "Green Valley Foods",
              "Kumar & Sons Hardware", "Apex Cloud Services", "Lotus Stationers", "Metro Print House",
              "Sunrise Electronics", "Patel Packaging Co"]
VENDORS_HI = ["शर्मा ट्रेडर्स", "ग्रीन वैली फूड्स", "कुमार एंड संस हार्डवेयर", "लोटस स्टेशनर्स",
              "सनराइज इलेक्ट्रॉनिक्स", "पटेल पैकेजिंग", "दिल्ली लॉजिस्टिक्स", "अपेक्स क्लाउड सर्विसेज़",
              "मेट्रो प्रिंट हाउस", "ब्राइट ऑफिस सप्लाईज़"]


def indian_group(x: float) -> str:
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{whole}.{frac}"


def western_group(x: float) -> str:
    return f"{x:,.2f}"


def make(rng: random.Random, lang: str, i: int) -> dict:
    inv_no = f"INV-{rng.choice([2024, 2025])}-{rng.randint(100, 9999):04d}"
    y, m, d = rng.choice([2024, 2025]), rng.randint(1, 12), rng.randint(1, 28)
    iso = f"{y:04d}-{m:02d}-{d:02d}"
    sub = round(rng.uniform(800, 250000), 2)
    if lang == "en":
        vendor = rng.choice(VENDORS_EN)
        cur = rng.choice(["INR", "INR", "USD"])
        rate = 0.18 if cur == "INR" else 0.10
        tax = round(sub * rate, 2)
        total = round(sub + tax, 2)
        g = indian_group if cur == "INR" else western_group
        sym = "Rs. " if cur == "INR" else "$"
        date_txt = rng.choice([f"{d} {EN_MONTHS[m-1]} {y}", f"{d:02d}/{m:02d}/{y}"])
        t = rng.randint(0, 2)
        if t == 0:
            text = (f"INVOICE\nInvoice No: {inv_no}\nDate: {date_txt}\nFrom: {vendor}\n"
                    f"Subtotal: {sym}{g(sub)}\nTax ({int(rate*100)}%): {sym}{g(tax)}\n"
                    f"Total Due: {sym}{g(total)}\nThank you for your business.")
        elif t == 1:
            text = (f"Tax Invoice # {inv_no} | Issued {date_txt} | Supplier: {vendor} | "
                    f"Net {sym}{g(sub)} + tax {sym}{g(tax)} | Grand Total ({cur}) {g(total)}")
        else:
            text = (f"{vendor}\nBill {inv_no}  dated {date_txt}\nAmount before tax {sym}{g(sub)}\n"
                    f"Tax {sym}{g(tax)}\nPlease pay {sym}{g(total)} within 15 days.")
    else:
        vendor = rng.choice(VENDORS_HI)
        cur = "INR"
        tax = round(sub * 0.18, 2)
        total = round(sub + tax, 2)
        date_txt = rng.choice([f"{d} {HI_MONTHS[m-1]} {y}", f"{d:02d}/{m:02d}/{y}"])
        t = rng.randint(0, 2)
        if t == 0:
            text = (f"चालान\nचालान संख्या: {inv_no}\nदिनांक: {date_txt}\nविक्रेता: {vendor}\n"
                    f"उप-योग: ₹{indian_group(sub)}\nजीएसटी (18%): ₹{indian_group(tax)}\n"
                    f"कुल देय राशि: ₹{indian_group(total)}\nधन्यवाद।")
        elif t == 1:
            text = (f"टैक्स इनवॉइस # {inv_no} | जारी तिथि {date_txt} | आपूर्तिकर्ता: {vendor} | "
                    f"कर से पहले ₹{indian_group(sub)} + कर ₹{indian_group(tax)} | कुल योग ₹{indian_group(total)}")
        else:
            text = (f"{vendor}\nबिल {inv_no}, तारीख {date_txt}\nकर रहित राशि ₹{indian_group(sub)}\n"
                    f"कर ₹{indian_group(tax)}\nकृपया 15 दिन में ₹{indian_group(total)} का भुगतान करें।")
    return {"id": f"{lang}-{i:02d}", "language": lang, "text": text,
            "expected": {"invoice_number": inv_no, "invoice_date": iso, "vendor_name": vendor,
                         "total_amount": total, "currency": cur}}


def build(n_per_lang: int = 20) -> list[dict]:
    rng = random.Random(42)
    return [make(rng, lang, i) for lang in ("en", "hi") for i in range(1, n_per_lang + 1)]


if __name__ == "__main__":
    items = build()
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items to {OUT}")
