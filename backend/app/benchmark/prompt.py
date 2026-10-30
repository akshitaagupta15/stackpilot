PROMPT_VERSION = "extract_v1"

SYSTEM = ("You extract structured data from invoices. Reply with ONLY a JSON object with exactly these keys: "
          "invoice_number (string), invoice_date (string, YYYY-MM-DD), vendor_name (string), "
          "total_amount (number, the final amount payable including tax), currency (ISO code like INR or USD). "
          "No explanation, no markdown.")


def build_messages(invoice_text: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Invoice:\n{invoice_text}"}]
